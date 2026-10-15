| model | RAG | correct | simple | join | time | trap (refused) | false refusals | 2nd attempts | median s/question |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | no | **22/40** | 6/10 | 5/10 | 3/10 | 8/10 | 0 | 3 | 6.1 |
| qwen2.5-coder:7b | yes | **37/40** | 9/10 | 8/10 | 10/10 | 10/10 | 1 | 1 | 8.6 |
| qwen2.5:7b-instruct | no | **17/40** | 7/10 | 3/10 | 5/10 | 2/10 | 0 | 3 | 6.1 |
| qwen2.5:7b-instruct | yes | **30/40** | 9/10 | 8/10 | 8/10 | 5/10 | 0 | 2 | 8.5 |
| qwen3:8b | no | **19/40** | 6/10 | 4/10 | 4/10 | 5/10 | 0 | 3 | 8.5 |
| qwen3:8b | yes | **34/40** | 10/10 | 8/10 | 10/10 | 6/10 | 0 | 3 | 12.4 |

Explanation run `qwen2.5-coder_7b_rag_explain`: 37/40 correct; 29/29 prose answers passed the number check, 0 fell back to the result table; median 12.1 s/question.
