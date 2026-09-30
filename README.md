# Exception Handling Mining and LLM Analysis Framework

## Overview
This repository provides a comprehensive framework for mining exception handling (EH) practices from open-source repositories and evaluating Large Language Models (LLMs) on EH-related tasks. The tool is designed to support empirical studies on how exceptions are handled in real-world software and how modern LLMs can assist in this process.

The framework supports multiple programming languages (Python, Java, TypeScript) and includes a specialized evaluation suite for assessing LLMs across four distinct EH-centric tasks.

## Key Features

- **Multi-language EH Mining:** Leverages `tree-sitter` to parse and extract EH metrics from Python, Java, and TypeScript codebases.
- **Detailed EH Metrics:** Extracts data on `try-except/catch` blocks, `finally` clauses, specific exception types, generic handlers, and more.
- **Advanced Python Analysis:** Features call graph generation and uncaught exception detection to identify potentially unhandled error paths.
- **LLM Evaluation Suite:** A robust pipeline for evaluating LLMs (e.g., GPT-4, Claude, Phi-4, Llama) on EH tasks:
  - **Task 1: EH Existence Prediction** – Determining if a function requires EH.
  - **Task 2: EH Block Location** – Identifying where `try` blocks should be placed.
  - **Task 3: Exception Recommendation** – Suggesting appropriate exception types to catch.
  - **Task 4: EH Code Generation** – Generating complete EH blocks or completing existing ones.
- **Automated Quality Assessment:** Evaluates LLM outputs using traditional (Accuracy, F1), code-specific (BLEU, CrystalBLEU, CodeBLEU), and static analysis metrics (Pylint violations).

## Repository Structure

```text
├── miner.py                # Main entry point for the EH mining engine
├── cli.py                  # Command-line interface definitions
├── miner_py_src/           # Language-specific mining logic
│   ├── python/             # Python-specific metrics and call graph analysis
│   ├── java/               # Java-specific metrics
│   └── typescript/         # TypeScript-specific metrics
├── llm/                    # LLM evaluation and analysis
│   ├── llm.py              # LLM interaction layer (supports OpenAI, Anthropic, Gemini, Ollama)
│   ├── llm_analysis.py     # Script for evaluating LLM outputs and calculating metrics
│   ├── data/               # Raw and processed results from LLM runs
│   └── data_human_eval/    # Datasets used for human validation
├── data/                   # Sample datasets and repository lists
├── requirements.txt        # Project dependencies
└── utils.py                # Shared utility functions
```

## Requirements

- **Software:** Python 3.10 or later, `git` (for repository cloning).
- **Hardware:** Standard modern computer; no specific high-end peripherals or massive storage required for basic mining. Large-scale mining may require additional RAM and storage.
- **Dependencies:** All Python dependencies are listed in the `requirements.txt` file (including `pycg` for Python call graph analysis).

## Installation

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Testing the Installation
To verify that the framework is installed and functioning correctly, you can run a test command using the provided CLI:
```bash
python miner.py --help
```
**Expected Output:**
You should see the help message displaying all available arguments and options for the `miner.py` script, confirming that the environment is correctly set up.

## Docker Installation (Recommended)

To ensure maximum reproducibility and avoid polluting your local environment, we provide a Docker setup. This ensures all system requirements (OS, Python 3.10, and Git) are perfectly met.

1. **Build the Docker image:**
   ```bash
   docker build -t exception-miner .
   ```

2. **Test the installation and Run the Interactive Pipeline:**
   By default, the container will run the new interactive pipeline script. Because it requires user input, you must use the `-it` flag. To persist the outputs to your local machine, you should mount the output directories:
   ```bash
   docker run --rm -it \
     -v $(pwd)/output:/app/output \
     -v $(pwd)/tmp:/app/tmp \
     -v $(pwd)/llm/output:/app/llm/output \
     -v $(pwd)/projects:/app/projects \
     exception-miner
   ```

3. **Running the LLM Analysis manually via Docker:**
   If you need to analyze outputs manually, you can override the default entrypoint:
   ```bash
   docker run --rm -v $(pwd)/llm/output:/app/llm/output exception-miner llm/llm_analysis.py
   ```

## Usage

### 1. Interactive Pipeline Wizard (Recommended)
To run the entire pipeline—from mining exception handlers to generating a statistically representative sample, executing LLMs, and analyzing the results—you can use the new interactive wizard.

```bash
python run_pipeline_interactive.py
```
This script will guide you through:
- **Configuring the miner:** Specify the input CSV, output folder, and target programming language.
- **Statistical Sampling:** After mining, the script calculates the true population ($N$) of instances containing `try-except` blocks. It then calculates the optimal sample size ($n$) required to achieve a **95% Confidence Level** with a **5% Margin of Error**, using the formula: `Interval = Mean ± 1.96 × (Standard Deviation / √n)`. It creates a balanced sample (`tmp/balanced_sample.csv`) automatically.
- **LLM Configuration:** Prompts for your chosen LLM provider (OpenAI, Anthropic, Gemini), model name, and API keys.
- **Execution & Analysis:** Automatically runs `llm/llm.py` followed by `llm/llm_analysis.py`, resolving paths seamlessly.

### 2. Mining Exception Handling Practices (Manual)
The miner takes a CSV file containing repository names and URLs as input.

```bash
python miner.py -in data/your_repositories.csv -lang python java typescript -o output_directory
```

**Input CSV format:**
The input CSV should have at least the columns `name` and `repo` (URL).

### 3. Evaluating LLM Performance (Manual)
The LLM analysis script evaluates pre-generated LLM responses stored in the `llm/output/` directory.

```bash
python llm/llm_analysis.py
```

This script calculates metrics like BLEU, CrystalBLEU, Accuracy, and runs Pylint to check for EH-related code smells in the generated blocks. Results are saved to `llm/output/metrics.csv`. Furthermore, syntax validity percentages for generated exception handlers (Task 4) are available in `llm/data/task4_syntax_validity.csv`.

### 4. Running LLM Tasks (Manual)
To generate new responses from LLMs manually, you can use the scripts within the `llm/` directory (ensure your API keys are configured in a `.env` file or environment variables).

## Accepted Paper
This repository is the official artifact for our accepted paper. 
- **Paper Link:** [INSERT LINK TO ACCEPTED PAPER / ARXIV HERE]

## License
The code in this repository is provided under the MIT License. Please refer to the `LICENSE` file for detailed terms.
