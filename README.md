# ytDown

Aplicativo para Windows 10 e 11 que extrai o áudio de vídeos do YouTube, guarda tudo numa biblioteca organizada e toca as músicas num player inspirado no Windows Media Player 7. Um app para Android recebe os áudios pela rede local.

## Instalação

1. Baixe o `ytDown-windows.zip` do Release e extraia o conteúdo para uma pasta.
2. Abra `ytDown\ytDown.exe`. Não é preciso instalar Python nem ffmpeg.

O `ytDown.exe` precisa da pasta `_internal` ao lado dele: para mover o app, leve a pasta `ytDown` inteira. Como o executável não tem assinatura digital, o Windows SmartScreen pode avisar "O Windows protegeu o computador" na primeira execução; clique em **Mais informações** e em **Executar assim mesmo**.

## Como usar

A janela tem a árvore de navegação à esquerda, o conteúdo no centro, a fila de reprodução à direita e a barra de reprodução embaixo. Na árvore, **Biblioteca** reúne Músicas, Artistas, Álbuns, Gêneros e Adicionadas recentemente; **Em reprodução**, **Playlists** e **Extrair** ficam na raiz. As setas acima do conteúdo percorrem o histórico, o caminho indica a seção atual e os números ao lado de cada item mostram as contagens.

### Extrair

1. Clique em **Extrair** na árvore.
2. Cole a URL do vídeo. Para extrair vários de uma vez, coloque uma URL por linha.
3. Escolha o formato (MP3, M4A, FLAC ou WAV) e, se quiser, preencha as informações do áudio.
4. Clique em **Extrair áudio** (ou tecle **Ctrl+Enter** na caixa de URLs).

Vários vídeos de uma vez:

- O botão **Colar** acrescenta o que está na área de transferência ao fim da lista. Enter pula de linha.
- Os vídeos são extraídos um de cada vez, na ordem da lista. Linhas em branco e URLs repetidas são ignoradas.
- Se algum vídeo falhar, os outros continuam. A lista mostra a situação de cada vídeo, e o resumo no fim explica cada falha.
- **Cancelar** interrompe o vídeo atual e os que ainda não começaram. Os áudios já salvos continuam na biblioteca.
- Com mais de um vídeo, o campo **Nome** fica desativado e cada áudio recebe o título do próprio vídeo. **Autor**, **Álbum**, **Gênero**, **Ano** e **Imagem de capa** valem para todos.
- Para extrair um álbum, marque **Numerar faixas na ordem da lista**: cada vídeo recebe o nº da sua posição (a partir do nº digitado em "Nº da primeira faixa", ou de 1).

Depois da extração:

- **Tocar agora** reproduz as faixas salvas na ordem da extração; **Ver na biblioteca** mostra somente as faixas desse lote.
- **Enviar para o celular** envia todos os áudios salvos da última extração.
- **Mostrar arquivo** abre a pasta do áudio no Explorador.
- **Adicionadas recentemente** reúne as extrações da sessão atual (inclusive substituições, sem importações) e recomeça vazia ao abrir o app.

Links de playlist, de canal e de transmissões ao vivo são recusados. Se a URL de um vídeo também tiver um parâmetro de playlist (`&list=...`), apenas esse vídeo é extraído.

### Informações do áudio

Estas informações são gravadas no arquivo de áudio, para aparecerem nos players, e organizam a biblioteca. Todas são opcionais:

| Campo | Se ficar vazio |
| --- | --- |
| Nome | Título do vídeo |
| Autor | Fica sem autor (pasta "Artista desconhecido") |
| Álbum | Fica sem álbum (pasta "Álbum desconhecido") |
| Gênero | Fica sem gênero; ao digitar, o app sugere os gêneros que já existem na biblioteca |
| Ano | Fica sem ano (precisa ter 4 dígitos) |
| Nº da faixa | Fica sem número (precisa ser maior que zero) |
| Imagem de capa | Imagem padrão (`assets\default_cover.jpg`) |

A capa pode ser JPG, PNG, WebP, BMP ou GIF. Ela é salva em JPEG, com no máximo 1000 pixels no lado maior, mantendo a proporção; áreas transparentes ficam brancas. Depois de cada extração concluída, os campos são limpos para que os dados de um áudio não passem para o próximo sem querer.

O formato WAV não tem um padrão oficial para essas informações: o app as grava, mas nem todo player as exibe. Para garantir a exibição, prefira MP3, M4A ou FLAC.

### A biblioteca

Todo áudio extraído vai para a **biblioteca**: a pasta `Música\ytDown`, organizada em `Artista\Álbum\NN - Título.ext`. O índice fica em `%APPDATA%\ytDown\library.db`.

- Para usar outra pasta, clique em **Opções** (embaixo da árvore) e em **Alterar...**. Os áudios que já estão na biblioteca vão junto para a pasta nova.
- Ao extrair de novo um vídeo que já está na biblioteca (mesmo que o link esteja em outro formato), o app pergunta: **Substituir** (o áudio novo fica no lugar do antigo, que vai para a Lixeira), **Manter os dois** ou **Cancelar**.
- Um nome de arquivo já ocupado ganha " (1)"; nenhum arquivo é substituído sem você pedir.
- Ao abrir o app, a biblioteca é verificada em segundo plano. Se um arquivo sumiu da pasta, a faixa aparece esmaecida como indisponível; se ele voltar, fica disponível outra vez. **Remover faixas indisponíveis** apaga somente os registros dessas faixas, depois de confirmar que os arquivos continuam ausentes.
- Extração, importação e mudança de pasta não acontecem ao mesmo tempo.

#### Importar extrações anteriores à 2.0

Use **Importar áudios extraídos...** na barra lateral. Adicione uma ou mais pastas com extrações antigas e clique em **Importar**. O app procura MP3, M4A, FLAC e WAV também nas subpastas e **copia** os arquivos para a biblioteca, preservando os originais, as etiquetas e as capas. Não há busca automática pela coleção do computador.

- Duplicatas são ignoradas pela URL de origem ou pelo conteúdo do arquivo (SHA-256), comparando com a biblioteca e com o próprio lote.
- Arquivos sem URL de origem são aceitos; sem título, usa-se o nome do arquivo.
- Ao cancelar, as faixas já importadas permanecem. O resumo mostra importadas, duplicadas e erros.

### Navegar na biblioteca

- **Músicas:** clique no cabeçalho para ordenar por título, artista, álbum, duração, gênero, ano, nº da faixa, data de inclusão, reproduções ou última reprodução. Arraste os cabeçalhos para reordenar as colunas e use o botão direito no cabeçalho para esconder ou mostrar cada uma; tudo isso fica salvo.
- **Busca** (Ctrl+F): filtra título, artista, álbum e gênero, sem diferenciar acentos ou maiúsculas; as palavras podem estar em campos diferentes. Esc limpa a busca.
- **Álbuns:** grade de capas, ordenável por álbum, artista, ano ou data de inclusão. Selecione uma capa e clique em **Abrir álbum** (ou Enter) para ver as faixas; duplo clique na capa toca o álbum. Capas ausentes usam a imagem padrão.
- **Artistas** e **Gêneros:** agrupam as faixas (faixas sem essa informação ficam num grupo "desconhecido"). O artista mostra seus álbuns e todas as faixas; **Tocar tudo** toca o grupo.

Em qualquer lista de faixas, selecione uma ou mais linhas (Ctrl ou Shift) e use o botão direito para: **Tocar**, **Tocar em seguida**, **Adicionar à fila**, **Adicionar à playlist**, **Enviar para o celular**, **Propriedades**, **Excluir da biblioteca** e, para uma faixa, **Mostrar no Explorer**. Duplo clique ou Enter toca a partir da faixa escolhida, com a lista exibida como fila.

### Tocar

- **Barra de reprodução:** tocar/pausar, anterior, próxima, aleatório, repetir (desligado → todas → uma), posição, volume e mudo. Anterior recomeça a faixa depois de 3 segundos; antes disso, volta para a faixa anterior.
- **Fila** (à direita): a faixa atual aparece em negrito. Arraste para reordenar, dê duplo clique para tocar, Delete remove as selecionadas e **Limpar** esvazia. Arraste faixas de Músicas para a fila para acrescentá-las. **Salvar playlist** guarda a fila na ordem exibida.
- **Em reprodução:** capa grande, informações da faixa e as próximas da fila. **Modo compacto** abre uma janela pequena, sempre no topo, com os controles.
- **Miniatura na barra de tarefas:** ao passar o mouse sobre o ícone do ytDown, aparecem os botões anterior, tocar/pausar e próxima.
- **Atalhos** na janela principal: Espaço tocar/pausar; Ctrl+Esquerda e Ctrl+Direita faixa anterior ou próxima; Ctrl+Cima e Ctrl+Baixo volume; Ctrl+M mudo; Ctrl+S aleatório; Ctrl+T repetição; Ctrl+L mostra ou esconde a fila; Ctrl+F busca; Alt+Enter propriedades. Os atalhos não atrapalham a digitação nos campos de texto. As teclas de mídia do teclado e o painel de mídia do Windows não são suportados.

Uma reprodução é contada ao ouvir metade da faixa ou quatro minutos, o que vier primeiro; pausas e trechos pulados não contam.

Ao fechar, o ytDown guarda volume, mudo, aleatório, repetição, fila, posição, tamanho da janela, larguras dos painéis, página e colunas. Na próxima abertura a faixa volta carregada, sem tocar: pressione Play para continuar.

### Playlists

- Crie playlists pelo **+ Nova playlist** ou pelo menu de contexto de Playlists na árvore. F2 renomeia; o menu também exclui (com confirmação).
- Para acrescentar faixas, arraste músicas para a playlist na árvore ou use **Adicionar à playlist** no menu das faixas. A mesma música pode aparecer mais de uma vez.
- Na página da playlist, arraste uma linha para reordenar, Delete remove as selecionadas e duplo clique toca a partir da linha. **Tocar** e **Enviar para o celular** usam a playlist inteira.
- **Playlists automáticas** (somente leitura): **Adicionadas nos últimos 30 dias**, **Mais tocadas** (até 50, das mais para as menos tocadas) e **Nunca tocadas**. **Salvar como playlist** cria uma cópia comum, que pode ser editada.

### Editar propriedades

Selecione uma ou mais faixas e escolha **Propriedades** (ou Alt+Enter). Com uma faixa, edite título, artista, álbum, gênero, ano, nº e capa. Com várias, marque **Alterar** apenas nos campos que devem valer para todas. As etiquetas do arquivo, a pasta na biblioteca, a lista e a fila são atualizadas.

Antes de alterar um arquivo, o app guarda uma cópia do original em `.ytdown-recovery`, dentro da pasta da biblioteca. Essas cópias não são apagadas automaticamente; veja [como recuperar](docs/recuperacao-edicao-propriedades.md).

### Excluir faixas

Selecione as faixas e pressione Delete ou escolha **Excluir da biblioteca**. Depois da confirmação, os arquivos vão para a Lixeira do Windows e as faixas saem da biblioteca, da fila e das playlists. Restaurar um arquivo da Lixeira não o devolve à biblioteca: importe-o de novo.

### Biblioteca no celular

O app para Android acessa as faixas da biblioteca do PC pela rede local.

1. Instale o `ytDown-celular.apk` no celular (Android 10 ou mais recente).
2. Conecte o celular e o PC à mesma rede Wi-Fi confiável e abra o ytDown nos dois aparelhos. Se o Windows perguntar, permita o acesso em redes privadas.
3. No primeiro acesso, clique em **Conectar celular** no PC, escolha o computador no app Android e informe o código de pareamento. Depois disso, o celular procura automaticamente um PC já pareado; se houver mais de um, escolha na lista.
4. A galeria exibe capa, título, artista e o estado de cada faixa. Toque em **Fazer Download** para baixá-la; pedidos simultâneos entram em fila. As faixas concluídas aparecem como **Sincronizado** e ficam em `Música/ytDown`.

O serviço permanece ativo enquanto o ytDown estiver aberto no PC. Após uma queda de rede, o Android tenta reencontrar o mesmo PC e preserva o pareamento. A fila de downloads é mantida durante a sessão do app e não sobrevive ao encerramento do processo.

Se o celular não encontrar o PC, informe no app o endereço mostrado em **Conectar celular**. Alguns roteadores bloqueiam a comunicação entre aparelhos; nesse caso, verifique o isolamento de clientes ou use uma rede que permita essa comunicação.

**Segurança:** o celular precisa estar pareado para acessar a biblioteca disponibilizada. A comunicação não é criptografada e não autentica o servidor; use uma rede confiável. Para desfazer os pareamentos no PC, apague `%APPDATA%\ytDown\pairing.json` com o ytDown fechado.

## Quando parar de funcionar

O YouTube muda com frequência, e isso pode quebrar o `yt-dlp`. Se os downloads começarem a falhar, gere o aplicativo de novo; o script instala a versão mais recente:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

O script precisa de Python 3 e do ffmpeg instalados (`winget install Gyan.FFmpeg`).

Se o Node.js ou o Deno estiver instalado, o `yt-dlp` pode usá-lo para lidar com as proteções do YouTube. O aplicativo também funcionou sem eles nos testes, mas alguns vídeos podem precisar de um desses programas.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe main.py                                  # executa sem empacotar
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .       # testes (HTTP local, sem serviços externos)
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1  # gera dist\ytDown
powershell -ExecutionPolicy Bypass -File scripts\build_android.ps1  # gera dist\ytDown-celular.apk
```

O app para Android precisa do JDK 17 e do Android SDK em `%LOCALAPPDATA%\Android`. Para usar somente dependências já instaladas ou em cache, acrescente `-Offline` aos scripts: o Windows não executa pip, e o Gradle usa `--offline` (o wrapper do Gradle precisa já estar no cache). O plano e as decisões da 2.0 estão em [`docs/arquitetura-2.0.md`](docs/arquitetura-2.0.md), e o roteiro de validação do lançamento em [`docs/jow-49-validacao.md`](docs/jow-49-validacao.md).

O cache de miniaturas das capas fica em `%LOCALAPPDATA%\ytDown\thumbs` e pode ser apagado a qualquer momento.

### Arquitetura

O código segue a Clean Architecture: está dividido em camadas, e cada camada só depende das que estão mais para dentro. As regras de negócio não conhecem yt-dlp, mutagen, Qt nem a rede, e por isso podem ser testadas sem eles. O teste `tests/unit/test_architecture.py` falha se alguma camada importar o que não deve.

```
main.py                    ponto de entrada (também usado pelo PyInstaller)
ytdown/
  domain/                  conceitos e regras puras: formatos, metadados, URLs, fila, playlists, erros
  application/             casos de uso (extração, biblioteca, importação, Playback, playlists, SharingSession)
    ports.py               interfaces de que os casos de uso precisam
  infrastructure/          implementações dessas interfaces
    youtube.py             download e conversão (yt-dlp + ffmpeg)
    tags.py, covers.py     etiquetas e capas (mutagen + Pillow)
    qt_audio_player.py     toca os áudios (QtMultimedia)
    sharing/               servidor HTTP/UDP para o celular e celulares pareados
    sqlite_*.py,           índice da biblioteca e playlists (SQLite) e a pasta gerenciada
      library_storage.py
    windows_taskbar.py     botões na miniatura da barra de tarefas
  presentation/            todos os textos mostrados ao usuário e as janelas
    qt/                    interface em Qt (PySide6): janela principal, páginas, diálogos
  bootstrap.py             escolhe as implementações e conecta as camadas
tests/
  unit/                    regras e casos de uso, com dublês das interfaces (tests/fakes.py)
  integration/             implementações reais: arquivos de áudio, SQLite, sockets, janelas Qt (offscreen)
  contracts/               baterias que toda implementação de um port precisa passar
assets/                    ícone, capa padrão e o tema visual (theme/: folha de estilo e ícones SVG)
scripts/                   scripts de build
licencas/                  licenças que acompanham o app (Qt/LGPLv3)
android/                   app para Android
```

O app para Android segue a mesma ideia, em `android/app/src/main/java/com/ytdown/receiver/`:

- `domain/`: modelos, regras dos nomes de arquivo, interfaces (`Ports.kt`) e o caso de uso `DownloadAudio`.
- `data/`: descoberta por UDP, cliente HTTP, gravação em Música/ytDown e tokens de pareamento.
- `ui/`: ViewModel, uma tela por arquivo e o tema.
- `AppContainer.kt`: escolhe as implementações e as entrega ao ViewModel.

Para adicionar uma funcionalidade, comece pelo caso de uso em `application` (ou em `domain/usecase` no Android). Se ele precisar de algo externo, declare uma interface em `ports`, implemente em `infrastructure` (ou `data`) e conecte em `bootstrap.py` (ou `AppContainer.kt`).

O APK é assinado com a chave de depuração deste computador. Isso basta para uso pessoal, mas não serve para publicar em lojas de aplicativos, e um APK gerado em outro computador não instala por cima deste sem desinstalar antes.

### Protocolo entre o PC e o celular

- Descoberta: o celular envia `YTDOWN_DISCOVER_V1` em broadcast UDP para a porta 47820, e o PC responde com seu nome, identificador e porta.
- `GET /api/info`: identifica o PC.
- `POST /api/pair`: troca o código de pareamento por um token.
- `GET /api/files`: lista os áudios compartilhados (exige o token).
- `GET /api/files/<id>`: baixa um áudio (exige o token).

O HTTP usa a porta 47821. O código muda após cada pareamento e após 5 tentativas erradas.

## Publicar uma nova versão

O app pronto não fica no repositório (o `ffmpeg.exe` tem mais de 100 MB). Ele é publicado como anexo de um Release do GitHub:

1. Feche o ytDown e gere o app: `scripts\build_windows.ps1` e, se o app do celular mudou, `scripts\build_android.ps1`.
2. Compacte: `Compress-Archive dist\ytDown dist\ytDown-windows.zip -Force`.
3. Publique: `gh release create vX.Y dist\ytDown-windows.zip dist\ytDown-celular.apk --title "ytDown X.Y"`.

## Licenças de terceiros

O app inclui o [FFmpeg](https://ffmpeg.org), em uma versão compilada por [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) e licenciada sob a GPLv3. O `scripts\build_windows.ps1` copia para `dist\ytDown\licencas\ffmpeg` a licença e o `README.txt` dessa versão, que indicam o código-fonte exato utilizado. Quem distribuir o app deve manter essa pasta junto.

A interface usa o [Qt](https://www.qt.io) por meio do [PySide6](https://doc.qt.io/qtforpython-6/) (Qt for Python), sob a LGPLv3. O script copia para `dist\ytDown\licencas\qt` o texto da LGPLv3 (e da GPLv3, que ela complementa), a versão usada e onde obter o código-fonte; esses arquivos ficam em `licencas\qt` no repositório. As bibliotecas do Qt vão sem modificações, como DLLs separadas na pasta `_internal`, e podem ser substituídas por outra versão compatível.

Também são usados [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [mutagen](https://github.com/quodlibet/mutagen) (GPLv2+), [Pillow](https://python-pillow.org) (licença MIT-CMU) e Python (licença PSF).

## Uso responsável

Baixe apenas conteúdo que você tem direito de usar. Os Termos de Serviço do YouTube e as leis de direitos autorais continuam valendo.
