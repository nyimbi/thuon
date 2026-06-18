#!/usr/bin/env python
"""Live smoke test: LongFormDocumentEngine against lfm2.5:latest via Ollama."""
import sys
import time
sys.path.insert(0, '.')

from core.ai_engine import OllamaModel
from capabilities.long_form_document_engine import LongFormDocumentEngine

def progress(stage, i, n):
	print(f'  [{stage}] {i}/{n}', flush=True)

print('=== LongFormDocumentEngine live test (lfm2.5:latest) ===\n')

ai     = OllamaModel(model_name='lfm2.5:latest')
engine = LongFormDocumentEngine(ai)

t0 = time.time()
result = engine.generate(
	topic           = 'AI Adoption Strategy for Mid-Market Professional Services Firms',
	document_type   = 'strategy',
	target_audience = 'C-suite executives and department heads',
	target_pages    = 4,          # ~1000 words — fast smoke test
	save_output     = True,
	on_progress     = progress,
)
elapsed = round(time.time() - t0, 1)

print(f'\n--- RESULT ---')
print(f'Status:        {result["status"]}')
print(f'Title:         {result["title"]}')
print(f'Word count:    {result["word_count"]:,}')
print(f'Sections:      {result["section_count"]}')
print(f'Exhibits:      {result["exhibit_count"]}')
print(f'Elapsed:       {elapsed}s')
print(f'Output path:   {result.get("output_path")}')

if result['issues']:
	print(f'\nIssues ({len(result["issues"])}) :')
	for iss in result['issues']:
		print(f'  ⚠ {iss}')
else:
	print('\nNo issues reported.')

print('\n--- TOC ---')
print(result['toc'][:800])

print('\n--- MARKDOWN EXCERPT (first 2000 chars) ---')
print(result['markdown'][:2000])

if result.get('index'):
	print('\n--- INDEX (first 500 chars) ---')
	print(result['index'][:500])
