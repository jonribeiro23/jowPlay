# JOW-49 — roteiro de validação da 2.0

Estado: roteiro executado em 10/11/2026 com o pacote final; **W6 (atalhos) e W7 (miniatura da
barra de tarefas) aguardam conferência manual**, e a máquina usada não é um Windows limpo (detalhes
abaixo). Todas as histórias das fases 1 a 4 estão em "Feito" no Jira (consulta de 10/11/2026).

## Registro de execução

Para cada execução anote data, testador, commit e alterações locais, SHA-256 e tamanho dos artefatos, Windows e Android (versão/modelo), hardware, rede, resultado de cada item (passou/falhou/bloqueado/não executado), evidência e defeito associado. Anote o tempo medido e condições para desempenho; não invente metas. Conclua apenas quando os critérios oficiais forem conferidos e todos os itens obrigatórios tiverem evidência satisfatória.

### Checkpoint local — 10/11/2026

Base `628f547`, alterações locais de documentação e scripts. Windows 10 build 19045, Python 3.14.7 instalado: **não é Windows limpo**. Em cópia isolada, build Windows offline passou com 488 testes Python (1 ignorado); build Android offline passou com 10 testes unitários. O SDK emitiu aviso de versões XML; o empacotamento Android informou uma biblioteca sem strip. Nenhum aparelho foi testado.

O exe abriu uma janela e fechou com código 0 em perfil e biblioteca descartáveis, com PATH limitado às pastas do Windows; isso é apenas smoke test, não valida reprodução nem instalação limpa. O primeiro smoke usou perfil isolado, mas a configuração inicial tinha BOM e foi ignorada; a biblioteca escolhida nessa tentativa não estava comprovadamente isolada. O segundo confirmou a configuração isolada após fechar. Não foram efetuadas importações ou exclusões nessas tentativas.

Artefatos na cópia temporária `ytdown-jow49-11acc35a03e24d419b253fe3f2bef321/dist`: pasta Windows 342.282.757 bytes, exe 12.814.500 bytes (SHA-256 `E3B2C7C49604A06B9E03E898BC2C2062BFA71A949F0DC57638DFC824B9F0C581`); APK debug 22.488.233 bytes (SHA-256 `BA56EDBA7F45EC611C9A339C68E2748E3976F01731CCFF72ED2DA42BDFD461FF`). O FFmpeg e suas licenças vieram do pacote local anterior. As modificações finais para isolar o cache do PyInstaller foram feitas após o build Windows; o build Android foi repetido com a versão final do script. Esses artefatos são temporários e não são release.

O primeiro build limpou o cache compartilhado do PyInstaller por causa de `--clean`; o script agora direciona o cache offline à cópia de build. Os artefatos anteriores de `dist` foram preservados. Restam os testes manuais e a conclusão das dependências oficiais no Jira.

### Execução com o pacote final — 10/11/2026

Código: `develop` com as correções desta rodada (ver "Defeitos encontrados"). Pacote: pasta
`dist\ytDown` com 166 arquivos e 342.296.755 bytes; `ytDown.exe` SHA-256
`D46C9B0BBA16114DC546E2DE26F0FFD50FB6D5DF5651068B8130CF140D0EC626`. APK:
`ytDown-celular.apk`, 22.513.053 bytes, SHA-256
`2072FBE64F67E6F3181474E7E12E0FB10839437CD24C6685E44DC113847C4FEC` (idêntico ao instalado no
aparelho; o app Android não mudou desde a 1.0).

Ambiente: Windows 10 Pro 19045, [hardware omitido]; celular Android, Android 15, na mesma
rede Wi-Fi. **Não é Windows limpo**: esta máquina tem Python e FFmpeg. O Windows Sandbox não está
disponível (recurso desligado e virtualização desativada na BIOS). Como aproximação, o exe rodou
com PATH só com as pastas do Windows e APPDATA, LOCALAPPDATA e biblioteca temporários; as DLLs
carregadas pelo processo vieram só do Windows e do pacote (a única outra foi a do Windows Defender).

Condução: UI Automation do Windows sobre o exe (nomes acessíveis do Qt), com cliques e rolagem
postados só na janela do processo de teste, sem teclado e sem roubar o foco, porque o PC estava
em uso. Por isso o app rodou com `QT_QPA_PLATFORM=windows:dialogs=none` (seletor de pastas do Qt
no lugar do nativo do Windows). Reprodução sempre no mudo.

| ID | Resultado | Evidência |
| --- | --- | --- |
| W1 | Passou | Abre sem Python e FFmpeg no PATH. Fechar e reabrir restaura página, fila (3 faixas), faixa e posição, volume 35 e mudo; a playlist continua lá. |
| W2 | Passou | 7 arquivos (MP3, M4A, FLAC, WAV, com e sem capa, acentos, subpasta, 1 duplicata): "Importadas: 6; duplicadas: 1; erros: 0". Na repetição: "Importadas: 0; duplicadas: 7". Originais com o mesmo SHA-256 antes e depois; arquivos em `Artista\Álbum\NN - Título`. |
| W3 | Passou | Contagens de Artistas e Gêneros corretas; busca sem acento e entre campos ("agua", "DULCE mar", "cao"); limpar a busca volta às 6 faixas; histórico ← ← → correto. |
| W4 | Passou | Grade de álbuns com as capas embutidas e a imagem padrão no álbum sem capa (captura de tela). |
| W5 | Passou | Seleção múltipla; "Adicionar à fila" e "Tocar em seguida" na posição certa; playlist criada com 3 faixas na ordem exibida, presente depois de reabrir. |
| W6 | Parcial | Controles da barra passaram: tocar/pausar, próxima, anterior (regra dos 3 s), posição, aleatório, repetir nos 3 estados, volume e mudo. **Atalhos de teclado não testados no exe** (exigem foco); cobertos por testes automatizados. |
| W7 | Pendente | Exige passar o mouse na barra de tarefas; não testado. |
| W8 | Passou (cancelar) | Cancelar a exclusão não altera nada. A confirmação não foi feita no exe para não usar a Lixeira real; ela é coberta por testes com lixeira falsa. |
| W9 | Passou | Faixa WAV sem etiquetas: nome, artista, álbum, ano e nº gravados no arquivo; arquivo movido para `Artista Validação\Álbum Validação\07 - Faixa Editada Ç.wav`; cópia em `.ytdown-recovery`; lista e playlist atualizadas. |
| W10 | Medido | Perfil com 5.000 faixas, 500 álbuns e 300 artistas: janela em 3,3 s; lista com as 5.000 em até 7,0 s; busca em até 2,0 s e limpar em até 2,2 s (com a pausa de digitação); Álbuns em 0,9 s; Artistas em 0,4 s; 171 MB de memória. Os tempos incluem a sobrecarga da UI Automation; não há metas oficiais. |
| M1 | Passou | Envio pelo detalhe do álbum; o celular descobriu "[PC e endereço omitidos]" pela rede; código errado recusado; código certo pareou. |
| M2 | Passou | 2 faixas baixadas, idênticas às da biblioteca (SHA-256), com título, artista, álbum, nº e duração no MediaStore; o PC marcou "Enviado". Depois de "Parar de compartilhar", o servidor fechou e o celular mostra "Sem conexão". Reprodução no celular não testada (para não fazer som). |
| M3 | Passou | Sem token ou com token falso, `/api/files` e `/api/files/1` respondem 401 pela rede local. |
| X1 | Passou | Extração real de 2 vídeos (Me at the zoo e Big Buck Bunny) como álbum numerado: `01 - ` e `02 - `, com autor, álbum, gênero, ano, nº e capa; campos limpos depois. Repetir com link `youtu.be` mostrou a pergunta de duplicata, e "Manter os dois" criou outra cópia. |

#### Defeitos encontrados e corrigidos nesta rodada

- **O app não encerrava ao fechar a janela** quando havia uma faixa carregada. A barra de reprodução
  pedia para esperar a thread das capas, a janela se escondia e, ao fechar já escondida, o Qt não
  saía (ele só sai ao fechar a última janela *visível*). O processo ficava aberto sem janela.
  Corrigido: a janela principal encerra o app ao fechar; testes com `app.exec()` real em subprocesso.
- **Botões padrão do Qt em inglês** ("OK/Cancel", "Yes/No", "Save"): a tradução `qtbase_pt_BR`
  ia no pacote, mas não era carregada. Agora é instalada ao abrir, e o build exige o arquivo.
- **Plurais**: "1 faixas", "1 álbuns", "faixa(s)". Corrigidos nas listas, na fila, nas playlists e
  na confirmação de exclusão.
- O build passou a exigir também o plugin de áudio do Qt (`ffmpegmediaplugin.dll`).

Observações sem correção: os campos de informações da página Extrair têm o mesmo nome acessível
(atrapalha leitores de tela), e a primeira linha da grade de álbuns encosta no cabeçalho.

## Preparação segura

1. Use conta ou máquina virtual Windows 10/11 descartável, limpa, sem Python e sem FFmpeg no PATH; registre versões e confira com `where.exe python` e `where.exe ffmpeg`. Não altere o PATH global. Use dados de teste, nunca a biblioteca pessoal. Separe cópias de áudios pequenos com e sem capa, acentos, vários artistas/álbuns/gêneros e duplicatas; mantenha os originais fora da biblioteca gerenciada.
2. Copie a pasta `dist\ytDown` inteira (incluindo `_internal` e `licencas`) e registre seu hash e tamanho; o exe sozinho não basta. A instalação e a execução são distintas do build, que precisa de Python e FFmpeg. Registre avisos de assinatura/SmartScreen sem desativar proteções globalmente.
3. Para celular, use aparelho Android 10+ de teste e APK identificado por hash. Ele é um **debug APK**, não uma versão assinada para publicação. Instale pelo método permitido no aparelho, sem sobrescrever dados de uma instalação pessoal; se houver conflito de assinatura ou dados pessoais, use outro aparelho/perfil e registre o bloqueio. PC e celular na mesma rede privada confiável; transporte HTTP não é criptografado. Não altere roteador ou firewall permanentemente; registre bloqueios.
4. Não execute extração de YouTube durante a rodada offline: ela exige rede externa. Registre como bloqueada e execute apenas em rodada futura explicitamente autorizada com vídeo de teste autorizado. Transferência local exige apenas LAN, não internet.

## Casos manuais

| ID | Ação | Resultado esperado |
| --- | --- | --- |
| W1 | Abrir o exe da pasta completa; navegar e fechar normalmente; reabrir. | Janela abre sem instalação de Python/FFmpeg, ícones/capa visíveis, sem erro; estado salvo é restaurado. Registrar ambiente realmente limpo. |
| W2 | Importar cópias de teste; conferir resumo e arquivos originais; repetir importação. | Itens aparecem na biblioteca, originais permanecem intactos, duplicatas são informadas. |
| W3 | Percorrer Músicas, Álbuns, Artistas, Gêneros e histórico; pesquisar acentos/campos e limpar busca. | Contagens e breadcrumb coerentes, navegação volta/avança, filtros corretos e fila preservada. |
| W4 | Abrir álbuns com e sem capa, rolar e reabrir; abrir grupo de artista e gênero. | Capas ou imagem padrão aparecem; detalhes e faixas correspondem aos grupos. |
| W5 | Selecionar múltiplas faixas, tocar, tocar em seguida e adicionar à fila; criar playlist e reabrir. | Ordem visual e duplicatas preservadas conforme ação, reprodução e playlist coerentes. |
| W6 | Testar barra, seek, volume, mudo, repetição, aleatório e atalhos locais; digitar em campo de texto. | Controles funcionam, estado visual acompanha; atalhos não capturam digitação. Não exigir SMTC/atalhos globais: não implementados. |
| W7 | No Explorer, testar miniatura da barra, botões e mudança de estado; fechar/reabrir. | Botões acompanham e controlam reprodução; registrar DPI e resultado. Ver também `jow-48-taskbar.md`. |
| W8 | Com cópias descartáveis, cancelar exclusão e verificar que nada mudou; confirmar exclusão de outra seleção de teste. | Cancelamento preserva dados; confirmação envia somente as cópias à Lixeira e remove registros/fila conforme aplicação. Não esvaziar Lixeira. |
| W9 | Examinar propriedades/edição de etiquetas e procurar ação no menu. | Registrar como pendente: JOW-43 preparou edição seletiva, não comprova editor completo; não marcar aceita apenas por ausência de erro. |
| W10 | Com coleção sintética representativa, registrar abertura, busca, rolagem, importação e responsividade. | Anotar tamanhos, tempos, hardware e percepção; comparar apenas com metas oficiais quando conhecidas. Benchmark offscreen não comprova fluidez do exe. |
| M1 | Abrir envio de uma seleção e de um álbum; abrir app no celular, descobrir PC ou informar endereço e parear com código. | Apenas faixas disponíveis selecionadas são listadas; pareamento funciona na LAN de teste. |
| M2 | Baixar áudio de teste, conferir nome, metadados, capa e reprodução no celular; fechar envio e tentar novamente. | Arquivo aparece em Música/ytDown e player; após fechamento não há sessão ativa. Registrar falhas de rede/permissão. |
| M3 | Testar código incorreto e acesso sem pareamento, sem acessar dados alheios. | Acesso negado; nenhum áudio de teste é baixado indevidamente. |
| X1 | Em rodada futura autorizada com rede externa, extrair vídeo de teste, repetir/cancelar e enviar ao celular. | Conversão, registro e tratamento de duplicata correspondem à interface; documentar rede, fonte e resultado. |

## Dependências no Jira

Na consulta de 10/11/2026, todas as histórias das fases 1 a 4 (inclusive JOW-30 a 35, 39, 41,
43, 44, 47 e 48) estavam em "Feito"; só os épicos e esta tarefa seguiam abertos.

## Build offline

Em uma cópia de trabalho isolada, com espaço suficiente e sem aplicativo aberto a partir do destino, use os scripts com `-Offline`. Windows precisa de `.venv` com requisitos e PyInstaller, além de FFmpeg no PATH; o script executa a suíte e substitui `dist\ytDown`. Android precisa do wrapper Gradle 8.9 e dependências já em cache, JDK 17 e SDK em `%LOCALAPPDATA%\Android`; o script roda testes e `assembleDebug` e substitui o APK no destino. `-Offline` não instala dependências nem busca artefatos remotos; cache insuficiente deve falhar. Preserve artefatos anteriores construindo em cópia isolada. A licença e a origem do FFmpeg devem acompanhar qualquer distribuição; avisos de licença ausente bloqueiam distribuição até resolução.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Offline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_android.ps1 -Offline
Get-FileHash dist\ytDown\ytDown.exe, dist\ytDown-celular.apk -Algorithm SHA256
```

O hash do exe não identifica os demais arquivos da pasta; arquive e identifique também o pacote completo. O Release só é publicado depois da aprovação do responsável.
