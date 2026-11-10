# Benchmark do workspace (JOW-47)

Execute, na raiz do projeto, com as dependências instaladas:

```powershell
.\.venv\Scripts\python scripts\benchmark_workspace.py
```

O resultado JSON vai para a saída padrão. `--count` e `--imports` permitem um ensaio menor; o padrão é 5.000 e 10. Cada execução cria uma pasta exclusiva com `TemporaryDirectory`, sem aceitar caminho de destino, e a remove ao terminar normalmente. Banco, preferências, arquivos, origem da importação e cache de capas ficam nela. Não usa dados, banco ou configurações reais. Uma interrupção abrupta pode deixar a pasta temporária `ytdown-benchmark-*` no diretório temporário do sistema.

Gera 5.000 WAV PCM válidos de 100 ms, com títulos, artistas, álbuns, números e imagens PNG incorporadas: 500 álbuns, 300 artistas e 500 cores de capa. O índice é construído diretamente, com gêneros sintéticos; a geração não é a importação medida. A importação mede dez WAVs adicionais distintos, incluindo leitura de metadados e comparação com os 5.000 arquivos existentes. Verificação chama o caso de uso diretamente. A janela é a composição real, com player falso e Qt offscreen; não inicia a verificação em segundo plano nem aplica o tema de produção. A construção e o primeiro `show` são cronometrados separadamente. Cada troca de página inclui `processEvents`; as páginas já foram construídas na abertura. Rolagem percorre 20 posições da barra, processando eventos em cada uma. Busca e ordenação chamam o modelo diretamente: não incluem o debounce de 250 ms nem digitação. Capas são assíncronas, e a rolagem não espera todas ficarem prontas. Operações incluem um `processEvents` após a chamada, não uma garantia de que todas as tarefas assíncronas terminaram.

## Medição nesta máquina

10/11/2026, Windows 10 build 19045, hardware omitido, Python 3.14.7, PySide6 6.12.0, Qt offscreen. Máquina com SSDs e HDD; unidade efetiva do diretório temporário e carga de fundo não foram caracterizadas. Uma execução antes e uma depois da alteração, sem repetição estatística; a suíte foi executada em paralelo com parte da segunda execução. Valores em segundos:

| Operação | Antes | Depois |
| --- | ---: | ---: |
| Construção da janela | 1,548 | 1,536 |
| Primeiro show | 0,071 | 0,092 |
| Busca de músicas (119 resultados) | 0,814 | 0,017 |
| Limpar busca | 0,906 | 0,170 |
| Ordenar músicas por artista | 0,908 | 0,183 |
| Ordenar álbuns por artista | 0,011 | 0,018 |
| Rolar músicas, 20 passos | 0,360 | 0,398 |
| Rolar álbuns, 20 passos | 0,080 | 0,139 |
| Verificar 5.000 arquivos | 3,613 | 4,950 |
| Importar 10 arquivos com 5.000 existentes | 49,725 | 39,811 |

Na segunda execução, troca para reprodução 0,009; músicas 0,030; recentes 0,012; artistas 0,260; álbuns 0,022; gêneros 0,202; playlists 0,006; extrair 0,021. Barras de rolagem tinham máximos 4.982 e 34.501. A verificação examinou 5.000, sem erros ou alterações; importação concluiu 10, sem erros ou duplicatas. A geração levou 24,390 s e não integra os tempos da aplicação.

Busca e ordenação antes disparavam o recarregamento dos resumos de todas as páginas por meio de `modelReset`. Agora apenas uma atualização explícita da biblioteca propaga esse recarregamento; mudanças de busca, ordenação e seleção de IDs continuam atualizando a tabela. A comparação sugere melhora nesse caminho, mas uma amostra e carga concorrente não permitem atribuir diferenças menores com confiança. A importação não foi extrapolada para importação de 5.000 arquivos.

## Importação: investigação e comparação posterior

No mesmo computador, um perfil da execução completa anterior à mudança mediu 41,110 s na importação, dos quais 36,087 s no cálculo de 5.010 hashes e 31,404 s abrindo os arquivos. O perfil acrescenta sobrecarga e não é diretamente comparável ao tempo sem instrumentação.

O cálculo dos hashes existentes agora usa até oito workers, com fila limitada. Continua lendo os arquivos integralmente com SHA-256 e aguardando todos antes de importar; erro de leitura interrompe a importação e arquivos ausentes continuam participando pela URL. O progresso é reportado na thread chamadora e a leitura continua cancelável por bloco. Na execução completa posterior, sem profiler, importar 10 arquivos com 5.000 existentes levou **6,068 s**, contra **39,811 s** na execução anterior sem profiler (redução observada de aproximadamente 85%). Ambas importaram 10 arquivos, sem erros ou duplicatas. São execuções únicas, com condições de cache e carga não controladas; na anterior houve testes em paralelo. Não é uma garantia para HDD, arquivos maiores ou rede. A deduplicação ainda lê todos os arquivos existentes e pode continuar cara em bibliotecas reais.

Esses tempos não medem o executável distribuído, inicialização de processo, player real, latência de entrada, quadros perdidos ou fluidez visual. Dados sintéticos curtos e cache de disco podem favorecer o resultado; verificação não mede arquivos ausentes, falhas ou unidades remotas. Não foram fornecidos limites de aceitação verificáveis nesta tarefa, portanto nenhuma meta de desempenho é considerada cumprida. Repetir em hardware e bibliotecas representativas e avaliar visualmente o executável para essas conclusões.
