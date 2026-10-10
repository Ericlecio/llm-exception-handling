import pandas as pd
import os

# Dicionário de metadados: mapeia o nome da coluna para a sua função no artigo
DESCRICAO_COLUNAS = {
    # --- COLUNAS DA BASE ORIGINAL ---
    "n_try_except": "Indica se o código original possuía bloco try/except (1 = Sim, 0 = Não). É a nossa variável alvo.",
    "str_code_without_try_except": "O snippet de código Python com o bloco try/except removido. Usado como input na Task 4.",
    "func_body": "O corpo completo da função Python original.",
    "project": "O nome do projeto de software de onde esse trecho de código foi extraído.",
    
    # --- COLUNAS ADICIONADAS PELO SEU SCRIPT LLM ---
    "task": "A tarefa que a IA executou (Ex: task4 = gerar apenas o bloco except).",
    "prompt_type": "O estilo de Engenharia de Prompt testado (Ex: style-qg-default = Quality Guided).",
    "llm_response": "A resposta bruta gerada pela Inteligência Artificial. É aqui que está o código que passará pelo Pylint.",
    "input_tokens": "Custo de entrada: Tamanho do texto enviado para a IA (contexto + prompt).",
    "output_tokens": "Custo de saída: Tamanho do texto gerado pela IA."
}

def analisar_datasets(caminho_original, caminho_gerado):
    print("="*70)
    print("🔍 INICIANDO RAIO-X DOS DADOS E DICIONÁRIO DE COLUNAS")
    print("="*70)

    # 1. Verificar se os arquivos existem
    if not os.path.exists(caminho_original):
        print(f"[ERRO] Dataset original não encontrado: {caminho_original}")
        return
    if not os.path.exists(caminho_gerado):
        print(f"[ERRO] Dataset gerado não encontrado: {caminho_gerado}")
        return

    # 2. Carregar os dados
    df_orig = pd.read_csv(caminho_original)
    df_ger = pd.read_csv(caminho_gerado)

    # 3. Análise de Volume (Linhas e Colunas)
    print("\n📊 1. VOLUME DE DADOS")
    print(f"Dataset Original: {len(df_orig)} linhas e {len(df_orig.columns)} colunas.")
    print(f"Dataset Gerado:   {len(df_ger)} linhas e {len(df_ger.columns)} colunas.")
    
    if len(df_orig) != len(df_ger):
        print("⚠️ ALERTA: O número de linhas está diferente! O script pode não ter terminado de rodar.")
    else:
        print("✅ SUCESSO: O número de linhas bate perfeitamente (1 para 1).")

    # 4. Dicionário de Dados (Originais vs Novas)
    colunas_originais = list(df_orig.columns)
    colunas_novas = list(set(df_ger.columns) - set(df_orig.columns))

    print("\n🧬 2. ESTRUTURA E DICIONÁRIO DE DADOS")
    
    print(f"\n🔹 COLUNAS ORIGINAIS (O que já veio na base - {len(colunas_originais)} colunas):")
    for col in colunas_originais:
        descricao = DESCRICAO_COLUNAS.get(col, "Dado nativo da extração original.")
        print(f"  • {col}: {descricao}")

    print(f"\n🔸 COLUNAS NOVAS (O que o seu script adicionou - {len(colunas_novas)} colunas):")
    if not colunas_novas:
        print("  Nenhuma coluna nova encontrada.")
    else:
        for col in colunas_novas:
            descricao = DESCRICAO_COLUNAS.get(col, "Coluna gerada pela IA durante os testes.")
            print(f"  • {col}: {descricao}")

    # 5. Integridade das Respostas da IA (O mais importante)
    print("\n🤖 3. INTEGRIDADE DAS RESPOSTAS DA IA (llm_response)")
    if 'llm_response' in df_ger.columns:
        total_respostas = len(df_ger)
        respostas_nulas = df_ger['llm_response'].isna().sum()
        
        # Conta respostas que não são nulas, mas estão vazias ou só têm espaços
        respostas_vazias = df_ger[df_ger['llm_response'].notna()]['llm_response'].apply(lambda x: str(x).strip() == '').sum()
        
        respostas_validas = total_respostas - respostas_nulas - respostas_vazias

        print(f"Total de linhas processadas: {total_respostas}")
        print(f"Respostas válidas geradas: {respostas_validas} ({(respostas_validas/total_respostas)*100:.1f}%)")
        print(f"Falhas (Nulas/None): {respostas_nulas}")
        print(f"Falhas (Textos vazios): {respostas_vazias}")
        
        if respostas_nulas > 0 or respostas_vazias > 0:
            print("⚠️ ALERTA: Algumas linhas falharam. O script precisará tentar novamente essas linhas no futuro.")
        else:
            print("✅ SUCESSO: 100% das linhas possuem respostas da IA preenchidas!")

    # 6. Análise de Custos/Tokens
    print("\n💰 4. CONSUMO DE TOKENS (MÉDIA)")
    if 'input_tokens' in df_ger.columns and 'output_tokens' in df_ger.columns:
        media_in = df_ger['input_tokens'].mean()
        media_out = df_ger['output_tokens'].mean()
        print(f"Média de Input Tokens enviados: {media_in:.0f} por snippet")
        print(f"Média de Output Tokens gerados: {media_out:.0f} por snippet")

    print("\n" + "="*70)
    print("🏁 ANÁLISE CONCLUÍDA")
    print("="*70)


if __name__ == "__main__":
    # Mantive os caminhos adaptados para rodar de dentro da pasta 'llm'
    ARQUIVO_ORIGINAL = "data/balanced_sample.csv"
    
    # Substitua pelo nome real do arquivo que foi gerado na sua pasta output
    ARQUIVO_GERADO = "llm/output/combined_claude-haiku-4-5_task4_style-default_results.csv" 
    
    analisar_datasets(ARQUIVO_ORIGINAL, ARQUIVO_GERADO)