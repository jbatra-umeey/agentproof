"""Isolated Python repair harness. Never executes submitted code on the host."""

import asyncio
import json
import uuid


class SandboxUnavailable(RuntimeError):
    pass


HARNESS = """import base64,json,os,resource,subprocess,sys,tempfile
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
data=json.loads(sys.stdin.read(100000))
with tempfile.TemporaryDirectory(dir="/tmp") as d:
    open(d+"/solution.py","w").write(data["source"])
    open(d+"/test_solution.py","w").write(data["tests"])
    with open(d+"/out.log","w+") as out:
        try:
            p=subprocess.run([sys.executable,"-B","-m","unittest","discover","-v","-s",d],cwd=d,stdout=out,stderr=out,timeout=15,env={"PATH":"/usr/local/bin:/usr/bin:/bin","PYTHONDONTWRITEBYTECODE":"1"})
            out.seek(0); log=out.read(16000)
            print(json.dumps({"passed":p.returncode==0,"exit_code":p.returncode,"log":log}))
        except subprocess.TimeoutExpired:
            print(json.dumps({"passed":False,"exit_code":124,"log":"Sandbox test timeout"}))
"""


class DockerSandbox:
    def __init__(self, settings):
        self.settings = settings

    def command(self, name):
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            "--pids-limit=64",
            "--memory=256m",
            "--memory-swap=256m",
            "--cpus=0.5",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
            "--log-driver=none",
            "-i",
            self.settings.sandbox_image,
            "python",
            "-I",
            "-c",
            HARNESS,
        ]

    async def run(self, source, tests):
        if not self.settings.sandbox_enabled:
            raise SandboxUnavailable(
                "SANDBOX_ENABLED=true and a dedicated Docker runner are required"
            )
        name = "agentproof-" + uuid.uuid4().hex
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.command(name),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable("Docker is unavailable; host execution is prohibited") from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(json.dumps({"source": source, "tests": tests}).encode()), 25
            )
            if proc.returncode != 0:
                raise SandboxUnavailable("Container execution failed")
            result = json.loads(stdout)
            if not isinstance(result.get("passed"), bool) or not isinstance(result.get("log"), str):
                raise SandboxUnavailable("Invalid sandbox result")
            return result
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise SandboxUnavailable("Sandbox failed or timed out") from exc
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            # Docker process death does not guarantee container death.
            cleanup = await asyncio.create_subprocess_exec(
                "docker",
                "rm",
                "-f",
                name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(cleanup.wait(), 10)
            except TimeoutError:
                cleanup.kill()
                await cleanup.wait()
