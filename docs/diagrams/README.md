# Diagram sources and renders

Eight `.mmd` Mermaid sources are paired with rendered `.svg` files. The HTML handbook embeds the SVGs and needs no network connection. Diagram validation results are in `evals/results/diagram-validation.json`.

To regenerate a diagram in a local environment with Node and Chromium:

```bash
npx --package @mermaid-js/mermaid-cli mmdc -i docs/diagrams/architecture.mmd -o docs/diagrams/architecture.svg
npm ci
npm run docs
```

Repeat the first command for each modified diagram. Rendering settings may differ from the original green/white theme; the Mermaid source is the semantic authority. The deployment diagram is a target topology, not evidence of a running deployment.
