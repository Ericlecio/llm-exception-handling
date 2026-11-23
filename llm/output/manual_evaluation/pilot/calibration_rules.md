# Regras de decisão da avaliação manual / Manual evaluation decision rules

As quatro regras abaixo foram acordadas pelos dois avaliadores depois do piloto (30 itens, fora da amostra principal) e aplicadas na avaliação principal (120 pares, 240 handlers). Elas complementam as definições das perguntas da planilha:

- **1a.** O tipo capturado pode ocorrer no `try`? (Sim / Não / Não é possível determinar)
- **1b.** A reação ao erro é apropriada para a função? (Sim / Não)
- **3.** Semelhança com o handler do desenvolvedor (1 a 5)

The four rules below were agreed on by the two raters after the pilot (30 items, outside the main sample) and applied in the main evaluation (120 pairs, 240 handlers). They complement the question definitions in the spreadsheet:

- **1a.** Can the caught exception occur in the `try` block? (Yes / No / Cannot be determined)
- **1b.** Is the reaction to the error appropriate for the function? (Yes / No)
- **3.** Similarity to the developer's handler (1 to 5)

---

## Regra 1 / Rule 1 — pergunta 1a: de onde vem a exceção / question 1a: where the exception comes from

**PT.** Responda **Sim** quando for possível apontar a instrução do `try` que pode lançar a exceção capturada, por uma de duas origens: (a) o próprio código da função (por exemplo, `int(v)` lança `ValueError`); ou (b) o comportamento documentado da biblioteca chamada (por exemplo, `Model.objects.get` lança `DoesNotExist`). Se não for possível apontar a instrução por nenhuma das duas origens, responda **Não é possível determinar**.

**EN.** Answer **Yes** when the statement in the `try` block that can raise the caught exception can be identified from one of two sources: (a) the function's own code (e.g., `int(v)` raises `ValueError`); or (b) the documented behavior of the library being called (e.g., `Model.objects.get` raises `DoesNotExist`). If the statement cannot be identified from either source, answer **Cannot be determined**.

**Exemplos do piloto / Pilot examples**

- **I3329** (`authenticate_credentials`): o handler captura `model.DoesNotExist`, que o Django documenta como a exceção lançada por `objects.get` quando o registro não existe → **Sim** (origem documentada). / The handler catches `model.DoesNotExist`, which Django documents as raised by `objects.get` when no record exists → **Yes** (documented source).
- **I4196** (`can_logger`): o handler captura `ValueError`, mas nenhuma instrução do `try` mostra, pelo código ou pela documentação, de onde esse erro viria → **Não é possível determinar**. / The handler catches `ValueError`, but no statement in the `try` block shows, from the code or the documentation, where it would come from → **Cannot be determined**.

## Regra 2 / Rule 2 — pergunta 1b: relançar / question 1b: re-raising

**PT.** Relançar o erro, ou embrulhá-lo numa nova exceção e relançar, é **apropriado** quando a função deve propagar o erro para quem a chamou. É **inadequado** quando impede uma etapa que o próprio código executaria depois de capturar o erro, como um mapeamento, um valor padrão ou uma limpeza.

**EN.** Re-raising the error, or wrapping it in a new exception and raising it, is **appropriate** when the function should propagate the error to its caller. It is **inappropriate** when it prevents a step that the code itself would perform after catching the error, such as error mapping, a default value or a cleanup.

**Exemplo do piloto / Pilot example**

- **I7822** (`get_credentials`, Azure SDK): o handler `except HttpResponseError: raise` relança o erro antes que o código faça o mapeamento do erro HTTP pelo código de status, então esse mapeamento nunca acontece → **Não**. / The handler `except HttpResponseError: raise` re-raises the error before the code maps it by HTTP status code, so the mapping never happens → **No**.

## Regra 3 / Rule 3 — pergunta 1b: erro anunciado pela função / question 1b: error announced by the function

**PT.** Se a função indica um caso de erro esperado (por exemplo, encerrar com Ctrl-C) e o handler não o cobre, a reação é **inadequada** (1b = Não).

**EN.** If the function signals an expected error case (e.g., exiting with Ctrl-C) and the handler does not cover it, the reaction is **inappropriate** (1b = No).

**Exemplo do piloto / Pilot example**

- **I5109** (`can_logger`): a função avisa "Press Ctrl-C to exit", mas o handler captura `Exception`. Como `KeyboardInterrupt` herda de `BaseException`, e não de `Exception`, o Ctrl-C passa pelo handler e o arquivo aberto não é fechado → **Não**. / The function prints "Press Ctrl-C to exit", but the handler catches `Exception`. Since `KeyboardInterrupt` inherits from `BaseException`, not `Exception`, Ctrl-C bypasses the handler and the open file is not closed → **No**.

## Regra 4 / Rule 4 — consistência entre itens / consistency across items

**PT.** Handlers **idênticos** da mesma função recebem as **mesmas respostas** em 1a, 1b e na nota, mesmo que estejam em grupos diferentes.

**EN.** **Identical** handlers of the same function receive the **same answers** for 1a, 1b and the rating, even if they appear in different groups.

**Exemplo do piloto / Pilot example**

- **I6697** e **I8477** (`authenticate_credentials`): dois modelos ou condições geraram exatamente o mesmo handler (`except models.AccessToken.DoesNotExist: raise exceptions.AuthenticationFailed(...)`), que portanto recebe as mesmas respostas. / Two models or conditions produced exactly the same handler, which therefore receives the same answers.

---

## Casos não cobertos / Uncovered cases

**PT.** Em casos que nenhuma regra cobre, o avaliador respondeu pelo próprio julgamento e começou a justificativa com "DÚVIDA:". Esses itens foram revistos no consenso, depois que os dois avaliadores terminaram, sem discussão durante a avaliação.

**EN.** In cases not covered by any rule, the rater answered by their own judgment and started the justification with "DÚVIDA:" ("DOUBT:"). These items were reviewed at consensus, after both raters finished, without discussion during the evaluation.
