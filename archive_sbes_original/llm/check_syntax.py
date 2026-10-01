import os
import csv
import ast

RESULTS_DIR = os.path.join(os.getcwd(), 'llm', 'output')
CSV_OUTPUT_PATH = os.path.join(os.getcwd(), 'llm', 'data', 'task4_syntax_validity.csv')

def check_syntax(llm_response):
    code = llm_response
    if '<code>' in code:
        code = code.split('<code>')[1].split('</code>')[0]
    elif '```python' in code:
        code = code.split('```python')[1].split('```')[0]
    code = code.strip()

    if code.startswith('except ') or code.startswith('except:') or code.startswith('finally:') or code.startswith('else:'):
        code = "try:\n    pass\n" + code

    try:
        ast.parse(code)
        return 1
    except SyntaxError:
        return 0

def main():
    task4_files = [f for f in os.listdir(RESULTS_DIR) if 'task4' in f and f.endswith('.csv')]
    
    os.makedirs(os.path.dirname(CSV_OUTPUT_PATH), exist_ok=True)
    
    results = []
    
    for f in sorted(task4_files):
        filepath = os.path.join(RESULTS_DIR, f)
        valid_count = 0
        total_count = 0
        
        with open(filepath, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                llm_response = row.get('llm_response', '')
                if not llm_response: continue
                
                total_count += 1
                valid_count += check_syntax(llm_response)
                    
        if total_count > 0:
            pct = (valid_count/total_count) * 100
            print(f"{f:70} -> {valid_count}/{total_count} ({pct:.1f}%)")
            
            # Extract model name from filename (e.g., combined_claude-haiku-4-5_task4_style-1-shot_results.csv)
            parts = f.split('_')
            model_name = parts[1] if len(parts) > 1 else 'unknown'
            prompt_style = parts[3] if len(parts) > 3 else 'unknown'
            
            results.append({
                'model': model_name,
                'prompt_style': prompt_style,
                'valid': valid_count,
                'total': total_count,
                'pct': f"{pct:.2f}"
            })
            
    with open(CSV_OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvout:
        writer = csv.DictWriter(csvout, fieldnames=['model', 'prompt_style', 'valid', 'total', 'pct'])
        writer.writeheader()
        writer.writerows(results)
        
    print(f"Results saved to {CSV_OUTPUT_PATH}")

if __name__ == '__main__':
    main()
