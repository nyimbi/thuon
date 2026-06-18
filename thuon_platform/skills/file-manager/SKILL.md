---
name: file-manager
description: |
  Read, write, list, and delete files on the local filesystem. Use when the
  user asks to "save this to a file", "read the file at", "list files in",
  "create a directory", "write output to", "delete file", or "show me what's
  in this folder".
when_to_use: |
  Invoke for: saving generated content to disk, reading existing files,
  listing directory contents, appending to logs, or any direct filesystem
  operation. Handles text files of any format (md, txt, csv, json, yaml).
argument-hint: "file operation: 'write X to /path/file.txt' or 'list /path/'"
arguments:
  - name: operation
    description: "write | read | list | delete | append"
    required: true
  - name: path
    description: "File or directory path"
    required: true
  - name: content
    description: "Content to write (for write/append operations)"
    required: false
  - name: pattern
    description: "Glob pattern for list (default: '*')"
    required: false
    default: "*"
metadata:
  author: anthropic
  version: "1.0.0"
  tags: [file, filesystem, read, write, save, list, directory, delete]

thuon:
  capability: file_writer
  method: write
  deps: []
  params: {}
  output_format: text
  category: data
  tier: 1
---

## File Manager Skill

Access the local filesystem via `file_writer`.

**Operation:** $ARGUMENTS

**Available operations:**

- **write**: `file_writer.write(file_path, content, mode='w', create_dirs=True)`
  Creates parent directories automatically.

- **read**: `file_writer.read_file(file_path, max_chars=50000)`
  Returns content. Reports truncation if file is larger than max_chars.

- **list**: `file_writer.list_files(directory, pattern='*', recursive=False)`
  Returns file names, paths, sizes. Supports glob patterns.

- **delete**: `file_writer.delete_file(file_path)`
  Confirms before deleting. Non-reversible.

- **append**: `file_writer.write(file_path, content, mode='a')`
  Appends to existing file without overwriting.

**Safety rules:**
- Confirm path with user before deleting
- For writes to important files, show the content before writing
- Report file size and location after successful writes
- For reads, summarize content rather than dumping raw bytes

