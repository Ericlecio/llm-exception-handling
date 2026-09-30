import os
import sys
import math
import subprocess
import pandas as pd

def calculate_sample_size(N, confidence_level=0.95, margin_of_error=0.05):
    """
    Calculates the sample size for a given population N, 
    confidence level, and margin of error.
    """
    # Z-score for 95% confidence is 1.96
    Z = 1.96
    p = 0.5
    e = margin_of_error
    
    # Cochran's formula
    n0 = (Z**2 * p * (1-p)) / (e**2)
    
    # Finite population correction
    if N > 0:
        n = n0 / (1 + (n0 - 1) / N)
        return math.ceil(n)
    return 0

def main():
    print("=" * 60)
    print("🚀 Exception Miner & LLM Evaluator - Interactive Pipeline")
    print("=" * 60)
    
    # ---------------------------------------------------------
    # 1. Ask for Miner Parameters
    # ---------------------------------------------------------
    print("\n[1/4] Configuring the Exception Miner")
    projects_csv = input("Enter the path to the projects CSV [projects.csv]: ").strip() or "projects.csv"
    
    if not os.path.exists(projects_csv):
        print(f"Error: Could not find {projects_csv}. Please make sure the file exists.")
        sys.exit(1)
        
    output_dir = input("Enter the output directory for miner [output]: ").strip() or "output"
    language = input("Enter the programming language (e.g., python, typescript, java) [python]: ").strip() or "python"
    
    # ---------------------------------------------------------
    # 2. Run Miner
    # ---------------------------------------------------------
    print(f"\nRunning miner on {projects_csv} for language '{language}'...")
    cmd = [
        sys.executable, "miner.py", 
        "--input_path", projects_csv, 
        "--output_dir", output_dir, 
        "--language", language
    ]
    subprocess.run(cmd)
    
    # ---------------------------------------------------------
    # 3. Calculate Population & Sample Size
    # ---------------------------------------------------------
    print("\n[2/4] Statistical Sampling Configuration")
    # Miner saves output to 'py', 'ts' or 'java' folders
    lang_dir = "py" if language == "python" else ("ts" if language == "typescript" else language)
    stats_dir = os.path.join(output_dir, "parser", lang_dir)
    if not os.path.exists(stats_dir):
        print(f"Error: {stats_dir} does not exist. The miner might have failed.")
        sys.exit(1)
        
    stats_files = [f for f in os.listdir(stats_dir) if f.endswith("_stats.csv")]
    if not stats_files:
        print(f"No stats files found in {stats_dir}.")
        sys.exit(1)
        
    dfs = []
    for f in stats_files:
        dfs.append(pd.read_csv(os.path.join(stats_dir, f)))
        
    df_all = pd.concat(dfs, ignore_index=True)
    
    # The relevant population for tasks 2-4 is functions containing EXACTLY one try-except block
    df_pos = df_all[df_all["n_try_except"] == 1]
    df_neg = df_all[df_all["n_try_except"] == 0]
    
    N = len(df_pos)
    suggested_n = calculate_sample_size(N)
    
    print(f"Total instances mined (Functions with try-except, Population N): {N}")
    print(f"Total instances without try-except: {len(df_neg)}")
    print(f"\nBased on a 95% confidence interval and a 5% margin of error:")
    print(f"Statistical formula used: n = (Z^2 * p * (1-p) / e^2) / (1 + (Z^2 * p * (1-p) / e^2 - 1) / N)")
    print(f"Suggested sample size (n): {suggested_n}")
    
    sample_size_input = input(f"\nEnter sample size to use [{suggested_n}]: ").strip()
    n_sample = int(sample_size_input) if sample_size_input else suggested_n
    
    # Generate the balanced sample for llm.py
    # We sample `n_sample` positive cases, and `n_sample` negative cases (if possible) 
    # so that llm.py can balance them properly.
    if n_sample < len(df_pos):
        sampled_pos = df_pos.sample(n=n_sample, random_state=42)
    else:
        sampled_pos = df_pos
        
    if n_sample < len(df_neg):
        sampled_neg = df_neg.sample(n=len(sampled_pos), random_state=42)
    else:
        sampled_neg = df_neg.sample(n=min(len(df_neg), len(sampled_pos)), random_state=42)
        
    df_balanced = pd.concat([sampled_pos, sampled_neg], ignore_index=True)
    
    os.makedirs("tmp", exist_ok=True)
    balanced_path = os.path.join("tmp", "balanced_sample.csv")
    df_balanced.to_csv(balanced_path, index=False)
    print(f"\nSaved balanced sample of {len(df_balanced)} rows to {balanced_path}")
    
    # ---------------------------------------------------------
    # 4. Ask for LLM parameters
    # ---------------------------------------------------------
    print("\n[3/4] LLM Configuration")
    provider = input("Enter LLM Provider (openai/anthropic/gemini) [openai]: ").strip().lower() or "openai"
    
    if provider == "openai":
        default_model = "gpt-4o-mini"
        env_var = "OPENAI_API_KEY"
    elif provider == "anthropic":
        default_model = "claude-haiku-4-5"
        env_var = "ANTHROPIC_API_KEY"
    elif provider == "gemini":
        default_model = "gemini-1.5-flash"
        env_var = "GEMINI_API_KEY"
    else:
        print("Unknown provider. Please run the script again and choose openai, anthropic, or gemini.")
        sys.exit(1)
        
    model = input(f"Enter model name [{default_model}]: ").strip() or default_model
    
    api_key = input(f"Enter {env_var} (leave blank if already loaded in environment or .env file): ").strip()
    if api_key:
        os.environ[env_var] = api_key
        
    limit = input("Optional: Limit number of samples per task for quick testing (leave blank for all): ").strip()
        
    # ---------------------------------------------------------
    # 5. Run LLM script and Analysis
    # ---------------------------------------------------------
    print("\n[4/4] Running LLM Evaluation & Analysis")
    
    print(f"Running LLM Evaluation (llm/llm.py) using model: {model}...")
    llm_cmd = [sys.executable, "llm/llm.py", "--models", model, "--project", "combined", "-v"]
    
    if limit.isdigit():
        llm_cmd.extend(["--limit", limit])
        
    subprocess.run(llm_cmd)
    
    print("\nRunning LLM Metrics Analysis (llm/llm_analysis.py)...")
    analysis_cmd = [sys.executable, "llm/llm_analysis.py"]
    subprocess.run(analysis_cmd)
    
    print("\n✅ Pipeline finished successfully! Results are saved in llm/output/")

if __name__ == "__main__":
    main()
