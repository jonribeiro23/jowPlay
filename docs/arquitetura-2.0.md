# ytDown 2.0: player e bibliotecas

O ytDown deixa de ser só um extrator e passa a ser um player com bibliotecas, no estilo do Windows Media Player do Windows 7. A diferença: a biblioteca **não lê as músicas do computador**. Ela contém apenas os áudios extraídos pelo ytDown.

As tarefas estão no Jira, no projeto [JOW](https://jonribeiro23.atlassian.net/jira/software/projects/JOW/boards/35). Cada épico corresponde a uma seção deste documento.

## Decisões

| Tema | Decisão | Motivo |
| --- | --- | --- |
| Interface | **Qt 6 (PySide6)** no lugar do Tkinter | Toca MP3, M4A, FLAC e WAV (QtMultimedia), tem listas e grades eficientes (model/view), arrastar e soltar e temas. Compatível com Python 3.14. |
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

`rel_path` é relativo à pasta da biblioteca, para que ela possa mudar de lugar. A URL de origem do vídeo também é gravada nas etiquetas do arquivo. É ela que identifica duplicatas e áudios extraídos antes da versão 2.0.

## Fluxos principais

- **Extrair:** baixa na pasta temporária, grava as etiquetas, move para `Artista\Álbum\NN - Título.ext` na biblioteca e registra no banco.
- **Editar propriedades:** regrava as etiquetas, move o arquivo se o artista, o álbum ou o título mudou, e atualiza o banco.
- **Tocar:** `Playback` monta a fila a partir da seleção e pede ao `AudioPlayer` a faixa atual. Ao passar de metade da faixa (ou de 4 minutos), conta uma reprodução.
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

## Riscos

- **Tamanho do app:** o Qt deve acrescentar cerca de 100 MB. O primeiro passo (spike) mede isso e define quais módulos excluir.
- **Formatos no QtMultimedia:** o Qt 6 no Windows usa FFmpeg para decodificar. O spike confirma MP3, M4A, FLAC e WAV, incluindo seek.
- **Áudios espalhados pelo disco:** extrações anteriores à 2.0 estão em pastas escolhidas pelo usuário. A importação os traz para a biblioteca.
