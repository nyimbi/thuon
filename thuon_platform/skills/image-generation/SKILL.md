---
name: image-generation
description: |
  Generate, describe, or analyze images. Use when the user asks to "create an
  image", "generate a picture", "draw", "visualize", "make a chart/diagram",
  "describe this image", or "analyze what's in this image".
when_to_use: |
  Invoke for: generating charts/graphs from data (via chart_generator),
  creating diagram descriptions (via diagram_generator), analyzing image
  content, or orchestrating image generation via external APIs.
argument-hint: "image description or data to visualize"
arguments:
  - name: prompt
    description: "Description of the image to generate, or data to chart"
    required: true
  - name: type
    description: "chart | diagram | description (default: chart)"
    required: false
    default: "chart"
  - name: chart_type
    description: "bar | line | pie | scatter (when type=chart)"
    required: false
    default: "bar"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [image, chart, visualization, diagram, graph, picture]

thuon:
  capability: chart_generator
  method: generate
  deps: []
  params: {}
  output_format: base64_image
  category: analytics
  tier: 2
---

## Image Generation Skill

Thuon supports data visualization via `chart_generator` and diagram descriptions
via `diagram_generator`. For pixel-level image generation, instruct the user
to connect an image generation API (Stable Diffusion, DALL-E, Midjourney).

**Request:** $ARGUMENTS

**Capabilities available:**

1. **Charts & graphs** (chart_generator):
   - bar, line, pie, scatter charts from data
   - Returns base64 PNG for display in UI
   - `chart_generator.generate(chart_type, {labels, values}, title)`

2. **Diagrams** (diagram_generator):
   - Architecture, flowchart, sequence diagrams as Mermaid/SVG
   - `diagram_generator.generate(diagram_type, description)`

**Instructions:**
- If the user provides data → generate a chart
- If the user describes a process → generate a diagram
- If pixel-level image is needed → explain Thuon's current scope and suggest an image API
- Always explain what the visualization shows

