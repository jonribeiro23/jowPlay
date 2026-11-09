# ytDown 2.0: player e bibliotecas

## Importação de extrações antigas (JOW-26)

`application/importing.py` compõe `ImportAudios` sobre `MetadataReader`,
`TrackRepository`, `LibraryStorage` e o novo port `ImportFiles`. Não depende de Qt.
O adaptador `FileSystemImportFiles` faz varredura explícita e recursiva sem seguir
links/junções, elimina sobreposição entre pastas e exclui a raiz gerenciada mesmo
quando sua pasta pai é selecionada. SHA-256 verifica bytes inalterados da biblioteca
e do lote; URLs são normalizadas com `canonical_video_url`. Nenhuma etiqueta é
reescrita e URL não é obrigatória para extrações da v1.

Cada arquivo é copiado em blocos de 1 MiB para staging dentro da raiz gerenciada
(mesma unidade), validado pelo MetadataReader e só então publicado e registrado.
O contexto do staging limpa temporários em sucesso, erro ou cancelamento; falha de
registro ou cancelamento após publicação descarta o destino. Faixas concluídas
permanecem após cancelar. Varredura, cópia e hash têm checkpoints canceláveis.
Arquivo candidato corrompido é erro por item. Arquivo existente ausente não possui
hash, mas sua URL continua no índice; outros erros de leitura do índice de hashes
encerram o lote antes de copiar, para não aceitar duplicatas sem verificação.

`ImportDialog` permite acumular várias pastas, executa o caso de uso em `QThread`
e recebe progresso por sinais. Só libera a thread após `finished` e `wait()`.
Cancelar/fechar durante o trabalho solicita cancelamento sem destruir o worker.
O bootstrap atualiza Songs inclusive após cancelamento parcial e acompanha os
diálogos no shutdown. A janela aguarda importação e mudança de pasta antes de
liberar serviços; a extração também verifica trabalho externo, além da modalidade
dos diálogos impedir operações concorrentes pela interface.

O ytDown deixa de ser só um extrator e passa a ser um player com bibliotecas, no estilo do Windows Media Player do Windows 7. A diferença: a biblioteca **não lê as músicas do computador**. Ela contém apenas os áudios extraídos pelo ytDown.

As tarefas estão no Jira, no projeto [JOW](https://jonribeiro23.atlassian.net/jira/software/projects/JOW/boards/35). Cada épico corresponde a uma seção deste documento.

## Decisões

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Interface | **Qt 6 (PySide6 Essentials + Addons)** no lugar do Tkinter | Toca MP3, M4A, FLAC e WAV (QtMultimedia, confirmado no spike JOW-9), tem listas e grades eficientes (model/view), arrastar e soltar e temas. Compatível com Python 3.14. |
| Arquivos | **Pasta gerenciada pelo app** (padrão: `Música\ytDown`), organizada em `Artista\Álbum\NN - Título.ext` | A biblioteca fica sempre consistente com o disco. Editar artista ou álbum move o arquivo. |
| Índice | **SQLite** (`sqlite3`, da biblioteca padrão) em `%APPDATA%\ytDown\library.db` | Consultas rápidas por artista, álbum, gênero e busca, sem dependência nova. |
| Fonte da verdade | **As etiquetas do arquivo** (nome, artista, álbum, capa...); o banco é um índice | Os arquivos continuam completos fora do app: no celular, em outro player ou em um backup. |
| Celular | O protocolo atual não muda | O app Android continua funcionando; só a origem dos arquivos enviados passa a ser a biblioteca. |

## Camadas

A regra continua a mesma: cada camada só depende das que estão mais para dentro. O teste `tests/unit/test_architecture.py` passa a proibir também `PySide6` em `domain` e `application`.

```
domain/          Track, Playlist, PlayQueue (fila, aleatório, repetir),
                 regras de nome de arquivo da biblioteca, regras de estatísticas
application/     casos de uso + ports
  ports          TrackRepository, PlaylistRepository, AudioPlayer, MetadataReader,
                 TagWriter, LibraryStorage, Settings (+ os ports atuais)
  library        RegisterExtractedTrack, ImportAudios, EditTracks, DeleteTracks,
                 CheckLibrary, BrowseLibrary (consultas)
  playback       Playback: une fila, player e estatísticas
  playlists      ManagePlaylists, playlists automáticas
  extraction     ExtractAudio/ExtractBatch (agora salvam na biblioteca)
  sharing        SharingSession (como hoje)
infrastructure/  SqliteTrackRepository, SqlitePlaylistRepository, QtAudioPlayer,
                 MutagenMetadataReader, FileSystemLibraryStorage (Lixeira do Windows),
                 JsonSettings + os adaptadores atuais (yt-dlp, mutagen, Pillow, servidor)
presentation/    Qt: MainWindow (casca), NavigationPane, páginas (Músicas, Artistas,
                 Álbuns, Gêneros, Playlist, Em reprodução, Extrair), PlayQueuePane,
                 TransportBar, diálogos (Propriedades, Enviar para o celular),
                 modelos Qt (QAbstractTableModel) sobre os casos de uso, texts.py
bootstrap.py     monta tudo
```

O `QtAudioPlayer` fica em `infrastructure`, atrás do port `AudioPlayer`. Assim, a lógica de reprodução (fila, próxima faixa, aleatório, estatísticas) é testada sem tocar áudio.

**Player (JOW-23):**
- **Port:** o `AudioPlayer` (em `application/ports.py`) carrega, toca, pausa, para, posiciona e controla volume (0–100, na escala do ouvido) e mudo.
- **Avisos:** posição, duração, estado, fim da faixa e erro chegam a um `PlayerListener`, na thread da interface.
- **Erros:** nada lança exceção. Arquivo ausente ou corrompido vira `on_error` com a mensagem para o usuário, e o player continua utilizável.
- **Um player só:** o `QtAudioPlayer` usa um único `QMediaPlayer` para todas as faixas, então trocar de faixa nunca deixa dois áudios tocando.
- **Testes:**
  - os testes do caso de uso usam o dublê `FakeAudioPlayer` (`tests/fakes.py`);
  - os de integração tocam arquivos reais, sempre no mudo;
  - neles, não use `QTest.qWait`: depois do aviso de fim de faixa do QtMultimedia, ele nunca mais volta e o teste trava (PySide6 6.12, Windows). Use `pause`/`wait_until` de `tests/qt_support.py`, que usam um `QEventLoop` comum.

### Threads

- Extração, importação e geração de miniaturas rodam fora da thread da interface (`QThreadPool`) e avisam por sinais Qt.
- O SQLite é acessado pela thread da interface nas consultas, que são rápidas. Trabalhos em lote usam uma conexão própria.

## Modelo de dados

```
tracks(id, rel_path UNIQUE, title, artist, album, genre, year, track_no,
       duration_ms, source_url, added_at, play_count, last_played_at, missing)
playlists(id, name, created_at)
playlist_items(playlist_id, position, track_id)
schema_version(version)
```

A tabela `tracks` também guarda colunas derivadas (nomes de exibição, textos sem acento e em minúsculas, indicador de "desconhecido"), calculadas pelas funções do domínio a cada gravação. Assim, busca, ordenação e resumos rodam em SQL, e o teste de contrato confere que os resultados batem com as regras de `domain/library.py`. As migrações ficam em `infrastructure/sqlite_library.py`: cada uma roda inteira ou não roda, e um banco de versão mais nova que o app é recusado com uma mensagem clara. Medição com 5.000 faixas: todas as consultas abaixo de 80 ms.

`rel_path` é relativo à pasta da biblioteca, para que ela possa mudar de lugar. A URL de origem do vídeo também é gravada nas etiquetas do arquivo (ID3 `WOAS`, MP4 `----:com.ytdown:source`, FLAC `YTDOWN_SOURCE`; a tabela completa está em `ytdown/infrastructure/tags.py`). É ela que identifica duplicatas. Por isso é gravado o endereço canônico informado pelo yt-dlp (`webpage_url`), igual para `youtu.be/X` e `youtube.com/watch?v=X`, e não o link exatamente como foi colado.

## Pasta gerenciada

- **Caminho:** `Artista/Álbum/NN - Título.ext`, definido em `domain/library_paths.py`. Campos vazios viram "Artista desconhecido", "Álbum desconhecido" e "Sem título". Caracteres proibidos no Windows (`<>:"/\|?*` e de controle) viram `_`. Pontos e espaços no fim são removidos. Nomes de dispositivo (CON, NUL, COM1...) ganham `_`.
- **Tamanho:** o caminho completo precisa caber nos 260 caracteres do Windows. O nome do arquivo encurta primeiro; depois, artista e álbum, até os mínimos de 20 e 10 caracteres.
- **Sem sobrescrever:** `FileSystemLibraryStorage` (em `infrastructure/library_storage.py`) nunca sobrescreve um arquivo; colisões ganham " (1)". Ele recusa caminhos que saiam da biblioteca (`..`, `C:`, `\`). Apaga pastas que ficam vazias e envia arquivos excluídos para a Lixeira do Windows.
- **Troca de pasta:** o caso de uso `ChangeLibraryFolder` move tudo com progresso. Se algo falhar no meio, os arquivos voltam para o lugar e nada muda: nem arquivos, nem índice, nem configuração.
- **Configurações:** ficam em `%APPDATA%\ytDown\settings.json` (`JsonSettings`), gravado de forma atômica. Um arquivo ilegível faz o app voltar aos valores padrão. A pasta padrão da biblioteca é `ytDown`, dentro da pasta Música real do usuário, mesmo que ela tenha sido redirecionada (ex.: OneDrive).

## Fluxos principais

- **Extrair:** baixa na pasta temporária, grava as etiquetas, move para `Artista\Álbum\NN - Título.ext` na biblioteca e registra no banco (`RegisterExtractedTrack`, JOW-19).
  - A extração entrega o arquivo a um *destino* (`AudioDestination`); no app, é `RegisterExtractedTrack.destination()`.
  - **Duplicatas:** antes de baixar, cada link é convertido no endereço canônico (`domain/urls.canonical_video_url`, igual ao `webpage_url` do yt-dlp) e procurado no banco. A pergunta (substituir, manter os dois, cancelar) é feita uma vez para a fila. *Substituir* mantém a faixa (id, data de inclusão, reproduções), usa o arquivo novo e manda o antigo para a Lixeira.
  - **Sem órfãos:** se o banco recusar a faixa, o arquivo recém-colocado é apagado (`LibraryStorage.discard`).
  - **Threads:** a extração registra a faixa fora da thread da interface; o `SqliteTrackRepository` serializa as operações com uma trava (`check_same_thread=False`).
  - **Pasta:** fica nas **Opções** (`presentation/qt/options_dialog.py`), que usa o `ChangeLibraryFolder` e não deixa mudar durante uma extração.
- **Editar propriedades:** regrava as etiquetas, move o arquivo se o artista, o álbum ou o título mudou, e atualiza o banco.
- **Tocar:** `Playback` monta a fila a partir da seleção e pede ao `AudioPlayer` a faixa atual. Ao passar de metade da faixa (ou de 4 minutos), conta uma reprodução.
  - **Fila** (`domain/play_queue.py`, JOW-22): guarda a ordem da lista (a que o usuário vê) e a de reprodução. A mesma faixa pode entrar duas vezes.
  - **Aleatório:** embaralha o resto, mantendo a faixa atual. Cada faixa toca uma vez por ciclo; com "repetir todas", cada ciclo é reembaralhado, sem repetir a última faixa logo no começo. Desligar volta à ordem da lista a partir da faixa atual.
  - **Repetir uma** só vale quando a faixa termina sozinha. Próxima e Anterior, pedidos pelo usuário, mudam de faixa e dão a volta na fila.
  - **Anterior** com mais de 3 s de faixa recomeça a faixa.
  - **Fim da fila:** sem repetir, a fila para.
  - **Caso de uso** (`application/playback.py`, JOW-24): `Playback` é o único ponto que a interface usa para tocar.
    - Comandos: tocar uma lista a partir de uma faixa, tocar/pausar, parar, próxima, anterior, posicionar, volume, mudo, aleatório, repetir e edição da fila.
    - Avisos por `PlaybackListener`: faixa atual, estado, posição, fila alterada e faixa indisponível.
    - Ao fim de uma faixa, a fila decide a próxima.
    - Faixa que não toca (arquivo sumido ou corrompido) é avisada e pulada, como se o usuário pedisse a próxima: com "repetir uma", não insiste nela. Se nenhuma faixa da fila toca, o player para, em vez de girar para sempre.
    - Avisos de uma faixa já trocada são ignorados.
    - A contagem de reproduções fica para a JOW-38.
- **Abrir o app:** `CheckLibrary` marca como indisponíveis as faixas cujo arquivo sumiu.
- **Importar:** lê áudios extraídos antes da 2.0, copia para a biblioteca e ignora duplicatas pela URL de origem ou pelo conteúdo.

## Fases

Cada tarefa no Jira tem a etiqueta da sua fase (`fase-1` a `fase-5`) e cita na descrição as tarefas de que depende.

| Fase | Entrega | Épicos |
| --- | --- | --- |
| 1 | App em Qt com a biblioteca registrando cada extração | JOW-1 Migração para Qt; JOW-2 Biblioteca; JOW-3 Metadados ampliados |
| 2 | Tocar músicas: lista, fila, controles, importação | JOW-4 Player; JOW-2 Biblioteca; JOW-5 Navegação (lista de músicas) |
| 3 | Navegar como no WMP: árvore, grade de álbuns, busca, "Em reprodução" | JOW-5 Navegação; JOW-4 Player |
| 4 | Playlists, edição de propriedades e envio ao celular a partir da biblioteca | JOW-6 Playlists; JOW-3 Metadados; JOW-7 Celular |
| 5 | Desempenho, acabamento e lançamento da 2.0 | JOW-8 Qualidade e lançamento |

Ordem sugerida para começar: **JOW-9** (spike), em paralelo com **JOW-10**, **JOW-11** e **JOW-12**, que não dependem do Qt.

## Resultado do spike (JOW-9)

Protótipo com `QMediaPlayer` + `QAudioOutput` (PySide6 6.12.0, Qt 6.12.0, Python 3.14.7), testado com arquivos reais gerados pelo ytDown (nome, autor e capa embutidos). Feito em 07/11/2026.

| Verificação | MP3 | M4A | FLAC | WAV |
| --- | --- | --- | --- | --- |
| Carrega e informa a duração (19.005 ms) | ✅ | ✅ | ✅ | ✅ |
| Toca, pausa e retoma | ✅ | ✅ | ✅ | ✅ |
| Seek para 12 s (posição exata: 12.000 ms) | ✅ | ✅ | ✅ | ✅ |
| Volume e mudo | ✅ | ✅ | ✅ | ✅ |
| Sinal de fim da faixa | ✅ | ✅ | ✅ | ✅ |
| Lê o título das etiquetas, com acentos | ✅ | ✅ | ✅ | ✅ |

- **Troca rápida de faixa:** 20 trocas seguidas, sem erro, com a última faixa tocando sozinha.
- **Ambientes:** passou rodando pelo Python, empacotado com PyInstaller (onedir) e empacotado sem Python nem ffmpeg no PATH. Não foi testado em uma máquina Windows limpa; isso fica para o teste final da 2.0 (JOW-49).
- **Tempo de carregamento:** de 11 ms a 108 ms por arquivo.

**Dependências:** o QtMultimedia **não** está no `PySide6-Essentials`. É preciso instalar também o `PySide6-Addons`. O Qt traz o próprio FFmpeg para decodificar (18,7 MB); o `ffmpeg.exe` do ytDown continua sendo usado só na conversão.

**Ruído no console:** o FFmpeg do Qt escreve informações dos arquivos no console. No app com janela isso não aparece; nos testes, silenciar com `QT_LOGGING_RULES="qt.multimedia.ffmpeg*=false"`.

### Tamanho do pacote

| Pacote do protótipo | Tamanho |
| --- | --- |
| PyInstaller sem ajustes | 131,5 MB |
| Com as exclusões abaixo (testado: tudo continua funcionando) | 88,0 MB |
| Parte do Qt no pacote enxuto (PySide6 + shiboken6) | 68,6 MB |

Arquivos que o PyInstaller inclui, mas o app não usa. O `scripts/build_windows.ps1` os exclui desde a JOW-21 (módulos com `--exclude-module`; DLLs, plugins e traduções apagados depois do build), junto com o Tkinter:

- `opengl32sw.dll` (19,7 MB, OpenGL por software)
- `Qt6Quick`, `Qt6Qml`, `Qt6QmlMeta`, `Qt6QmlModels`, `Qt6QmlWorkerScript`, `Qt6VirtualKeyboard` (QML e teclado virtual)
- `Qt6OpenGL`, `Qt6MultimediaWidgets` e o `QtMultimediaWidgets.pyd` (vídeo)
- plugins `platforminputcontexts`, `tls`, `networkinformation`
- plugins de plataforma `qdirect2d`, `qoffscreen` e `qminimal` (só o `qwindows` é necessário no app; os testes usam `offscreen` pelo Python, não pelo pacote)
- traduções do Qt, exceto `qtbase_pt_BR.qm` e `qtmultimedia_pt_BR.qm`

**Não excluir:** `Qt6Svg`, o plugin `iconengines\qsvgicon` e o `imageformats\qsvg`. Os ícones do tema (JOW-18) são SVG e ficariam em branco sem eles.

## Tema visual (JOW-18)

- `presentation/qt/theme.py` guarda **todas** as cores (`COLORS`) e medidas (`METRICS`). Nenhuma outra tela define cor ou tamanho de fonte; um teste (`tests/integration/test_qt_theme.py`) falha se alguém fizer isso.
- `assets/theme/ytdown.qss` é a folha de estilo. Ela só usa nomes entre chaves duplas, como `{{accent}}`, que o `theme.render_stylesheet` troca pelos valores (um nome desconhecido é erro). Atenção: escreva `QSlider::handle:focus`, nunca `QSlider:focus::handle`, que o Qt aplica ao widget inteiro (o teste também verifica).
- `assets/theme/icons/` tem os ícones próprios, em SVG, só com as cores `icon` e `icon_muted`. No código, `theme.icon("play")`.
- Mensagens com cor usam `theme.set_tone(widget, "error" | "success" | "neutral")`.
- O tema usa o estilo Fusion, a paleta escura do `theme.palette()` e o esquema de cores escuro do Windows (barra de título escura). O contraste segue o WCAG 2.1 (4,5:1 para texto, 3:1 para o foco), verificado nos testes.

**Estimativa para o ytDown 2.0:** cerca de 327 MB descompactado (hoje: 263 MB) e cerca de 140 MB no `.zip` do Release (hoje: 113 MB). O maior item continua sendo o `ffmpeg.exe` de conversão, com 212 MB.

**Conclusão:** o Qt atende ao player. Não é preciso um backend de áudio alternativo.

## Riscos

- **Tamanho do app:** medido no spike; ver "Tamanho do pacote" acima.
- **Licença do Qt:** PySide6 e o FFmpeg do Qt são LGPLv3. Desde a JOW-21, o build copia `licencas/qt` (LGPLv3, GPLv3, onde obter o código-fonte) e a versão usada para `dist\ytDown\licencas\qt`. As DLLs do Qt ficam separadas e sem modificações, como a LGPL pede.
- **Áudios espalhados pelo disco:** extrações anteriores à 2.0 estão em pastas escolhidas pelo usuário. A importação os traz para a biblioteca.

## Lista de músicas (JOW-25)

`SongsPage` usa `QTableView` e `TrackTableModel` sobre `TrackRepository`. Os dados são consultados uma vez por atualização ou ordenação, com `TrackQuery`; pintar uma célula não consulta SQLite nem o disco. A tabela mantém seu viewport e rolagem interna mesmo dentro do `QScrollArea` da janela. O teste offscreen monta a janela com 5.000 faixas reais no SQLite e verifica contagem, ordenação e rolagem.

A busca no cabeçalho usa Ctrl+F, Esc para limpar e debounce de 250 ms. A janela
encaminha o texto às páginas que oferecem `set_search_text`; Músicas aplica-o
em `TrackQuery`, preservando ordenação, seleção e fila. O SQLite compara palavras
normalizadas em título, artista, álbum e gênero. Álbuns filtra nome e artista;
Artistas permanece provisória.

O estado do cabeçalho (visibilidade, ordem, largura e ordenação) fica em `songs.header`, na mesma instância de `JsonSettings` usada pelo caso de uso de alteração da pasta. Seleção e faixa atual são preservadas por ID ao atualizar ou ordenar. O sinal `extraction_finished` atualiza a página também nos encerramentos parciais.

A árvore mostra contagens dos repositórios de faixas e resumos de artistas, álbuns e gêneros. A atualização do modelo de músicas também atualiza essas contagens após extração, importação, verificação e remoção. O histórico da janela alimenta as setas e o breadcrumb; `navigation.last_page` compartilha o mesmo `Settings` e valores inválidos retornam a Músicas. Playlists permanece uma página reservada, pois ainda não há repositório implementado.

## Integridade da biblioteca (JOW-27)

`CheckLibrary` roda numa `QThread` depois que a janela abre e sincroniza o campo `Track.missing` com os arquivos da pasta gerenciada. A raiz inteira indisponível não prova que todas as faixas foram apagadas: a checagem não escreve no índice e a interface mostra um único aviso. Erros pontuais de acesso também preservam o último estado da faixa. `RemoveUnavailableTracks` confirma novamente a ausência antes de remover apenas o registro; as cópias da faixa que estavam na fila de reprodução são purgadas pelo ID.

`build_main_window` conecta as páginas aos serviços compartilhados. O bootstrap cria um único `QtAudioPlayer` e um `Playback`; fechar a janela para a reprodução e chama `shutdown()` para liberar o arquivo, depois de cancelar e aguardar eventual extração. Os objetos multimídia pertencem à QApplication. Ao carregar uma faixa já enfileirada, Playback consulta seu registro atualizado, evitando caminhos antigos após uma extração com Substituir; a ordem da fila permanece a original. Os itens ainda não carregados da fila são snapshots e são atualizados no momento de carregar. A faixa corrente exposta e sua duração de fallback usam os metadados carregados.

## Barra de reprodução (JOW-28)

`MainWindow()` permanece utilizável sem serviços, com controles de transporte desabilitados. `build_main_window` chama `TransportBar.bind` com o mesmo `Playback` de `SongsPage`, um callback de `MetadataReader.read_cover` que resolve o caminho pelo storage e o `QPixmap` da capa padrão criado na thread da UI. Todos os comandos passam pelo Playback. O aviso opcional `PlaybackSettingsListener.on_settings_changed` sincroniza volume já limitado pelo player, mudo e repetição inclusive quando alterados fora da barra, sem exigir mudanças nos listeners antigos. `remove_listener` permite desligar a barra ao fechar ou destruir a janela, e seu adaptador mantém apenas uma referência fraca ao widget.

O painel `PlayQueuePane` usa o mesmo Playback: exibe a ordem da lista e marca a posição atual, mesmo com duplicatas ou aleatório. Identidades opacas das entradas preservam seleção e foco quando a fila muda externamente, sem confundir cópias da mesma faixa. Os avisos de fila e faixa redesenham o painel; duplo clique, Delete, limpar e arraste interno usam posições do Playback. O arraste de Músicas acrescenta as linhas selecionadas na ordem visível. O listener é removido ao fechar ou destruir o painel. Salvar playlist permanece desabilitado.

Durante o arraste, os avisos do relógio não movem o slider; soltar envia um único seek. Mudanças por teclado também enviam seek. A sincronização programática bloqueia os sinais dos sliders para evitar comandos de retorno. A barra mostra posição/duração reais, estado tocar/pausar, aleatório e os três modos de repetição.

Capas são lidas e decodificadas em um worker daemon, sem acesso ao repositório SQLite, com uma única leitura ativa e no máximo um pedido pendente (o mais recente). O resultado é uma `QImage` reduzida; a conversão para `QPixmap` ocorre apenas na UI. Um identificador crescente descarta respostas de faixas antigas. Fechar ou destruir remove o listener, invalida respostas e sinaliza o worker, sem esperar por uma leitura de arquivo em andamento. Capas ausentes, inválidas ou com erro usam o asset padrão. Não há cache persistente nem gravação de preferências de reprodução.

`test_qt_transport_bar` usa a composição real do bootstrap em offscreen com `FakeAudioPlayer`: tocar via Músicas, comandos e alterações externas, seek por arraste/teclado, capas atrasadas/ilegíveis e fechamento/destruição. Os testes de Playback também verificam a compatibilidade do aviso opcional e sua remoção.

### Miniaturas de capas

`ThumbnailCache` é a porta de aplicação; `FileThumbnailCache` lê capas pelo `MetadataReader`, usa Pillow e persiste PNGs por hash dos bytes originais em `%LOCALAPPDATA%/ytDown/thumbs`. `request` enfileira trabalho fora da interface; `get_or_create` e `cleanup` são operações bloqueantes para workers. A limpeza exige snapshot completo e estável dos caminhos da biblioteca, interrompe antes de excluir se qualquer leitura falhar e só remove nomes reconhecidos do cache. A edição de capa é futura.

## Álbuns (JOW-33)

`AlbumsPage` apresenta uma grade `QListView` com viewport próprio. Agrupa pelo nome de exibição e artista, usa a primeira faixa na ordem do álbum para a capa e ordena as faixas por número, com ausentes no fim. A ordenação por inclusão usa a primeira data de cada grupo, mais recente primeiro. O detalhe usa o mesmo Playback e o breadcrumb inclui o nome do álbum; o histórico continua sendo por página. A busca normalizada filtra o nome e o artista do álbum inteiro.

As capas são solicitadas sob demanda pela grade e resolvidas em um executor de uma thread usando o cache JOW-31; a interface usa a capa padrão enquanto espera ou em caso de erro. A atualização invalida resultados antigos e o fechamento cancela tarefas pendentes sem bloquear a interface. O teste offscreen exercita 500 álbuns, ordenação, busca, reprodução e rolagem.
# Navegação por artistas e gêneros

`GroupsPage` usa os resumos do domínio e consultas do repositório para agrupar e filtrar artistas e gêneros. A busca seleciona grupos que contenham alguma faixa correspondente; detalhes e contagens incluem todo o grupo. O refresh da página de músicas também atualiza os grupos após alterações da biblioteca.
