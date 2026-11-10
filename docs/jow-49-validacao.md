# JOW-49 — roteiro de validação da 2.0

Estado: preparação e verificações locais; **não aprovado para release**. Os critérios da JOW-49 foram consultados no Jira: exigem teste em Windows limpo, execução do roteiro sem falhas e publicação dos dois artefatos. As tarefas JOW-30, 31, 32, 33, 34, 35, 39, 41, 43, 44 e 47 estavam em andamento na consulta de 10/11/2026. Antes do lançamento, confira novamente a matriz completa no Jira; não interprete commits como conclusão das dependências.

## Registro de execução

Para cada execução anote data, testador, commit e alterações locais, SHA-256 e tamanho dos artefatos, Windows e Android (versão/modelo), hardware, rede, resultado de cada item (passou/falhou/bloqueado/não executado), evidência e defeito associado. Anote o tempo medido e condições para desempenho; não invente metas. Conclua apenas quando os critérios oficiais forem conferidos e todos os itens obrigatórios tiverem evidência satisfatória.

### Checkpoint local — 10/11/2026

Base `628f547`, alterações locais de documentação e scripts. Windows 10 build 19045, Python 3.14.7 instalado: **não é Windows limpo**. Em cópia isolada, build Windows offline passou com 488 testes Python (1 ignorado); build Android offline passou com 10 testes unitários. O SDK emitiu aviso de versões XML; o empacotamento Android informou uma biblioteca sem strip. Nenhum aparelho foi testado.

O exe abriu uma janela e fechou com código 0 em perfil e biblioteca descartáveis, com PATH limitado às pastas do Windows; isso é apenas smoke test, não valida reprodução nem instalação limpa. O primeiro smoke usou perfil isolado, mas a configuração inicial tinha BOM e foi ignorada; a biblioteca escolhida nessa tentativa não estava comprovadamente isolada. O segundo confirmou a configuração isolada após fechar. Não foram efetuadas importações ou exclusões nessas tentativas.

Artefatos na cópia temporária `ytdown-jow49-11acc35a03e24d419b253fe3f2bef321/dist`: pasta Windows 342.282.757 bytes, exe 12.814.500 bytes (SHA-256 `E3B2C7C49604A06B9E03E898BC2C2062BFA71A949F0DC57638DFC824B9F0C581`); APK debug 22.488.233 bytes (SHA-256 `BA56EDBA7F45EC611C9A339C68E2748E3976F01731CCFF72ED2DA42BDFD461FF`). O FFmpeg e suas licenças vieram do pacote local anterior. As modificações finais para isolar o cache do PyInstaller foram feitas após o build Windows; o build Android foi repetido com a versão final do script. Esses artefatos são temporários e não são release.

O primeiro build limpou o cache compartilhado do PyInstaller por causa de `--clean`; o script agora direciona o cache offline à cópia de build. Os artefatos anteriores de `dist` foram preservados. Restam os testes manuais e a conclusão das dependências oficiais no Jira.

## Preparação segura

1. Use conta ou máquina virtual Windows 10/11 descartável, limpa, sem Python e sem FFmpeg no PATH; registre versões e confira com `where.exe python` e `where.exe ffmpeg`. Não altere o PATH global. Use dados de teste, nunca a biblioteca pessoal. Separe cópias de áudios pequenos com e sem capa, acentos, vários artistas/álbuns/gêneros e duplicatas; mantenha os originais fora da biblioteca gerenciada.
2. Copie a pasta `dist\ytDown` inteira (incluindo `_internal` e `licencas`) e registre seu hash e tamanho; o exe sozinho não basta. A instalação e a execução são distintas do build, que precisa de Python e FFmpeg. Registre avisos de assinatura/SmartScreen sem desativar proteções globalmente.
3. Para celular, use aparelho Android 10+ de teste e APK identificado por hash. Ele é um **debug APK**, não uma versão assinada para publicação. Instale pelo método permitido no aparelho, sem sobrescrever dados de uma instalação pessoal; se houver conflito de assinatura ou dados pessoais, use outro aparelho/perfil e registre o bloqueio. PC e celular na mesma rede privada confiável; transporte HTTP não é criptografado. Não altere roteador ou firewall permanentemente; registre bloqueios.
4. Não execute extração de YouTube durante a rodada offline: ela exige rede externa. Registre como bloqueada e execute apenas em rodada futura explicitamente autorizada com vídeo de teste autorizado. Transferência local exige apenas LAN, não internet.

## Casos manuais (todos pendentes até registro individual)

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

## Dependências a conferir no Jira

Todas estão **pendentes de confirmação de status e critérios oficiais**; os títulos abaixo vêm do histórico local. A existência de commit ou teste automatizado não substitui a validação manual nem demonstra que a dependência foi concluída no Jira.

- [ ] JOW-30 — navegação, histórico e contagens: W3.
- [ ] JOW-31 — cache compartilhado de miniaturas: W4; ver também testes de cache e falhas de leitura.
- [ ] JOW-32 — busca instantânea: W3.
- [ ] JOW-33 — grade de álbuns e capas: W4.
- [ ] JOW-34 — navegação por artista e gênero: W3–W4.
- [ ] JOW-35 — ações de reprodução no menu: W5.
- [ ] JOW-39 — atalhos locais: W6; controles globais/SMTC seguem sem implementação.
- [ ] JOW-41 — exclusão de faixas: W8 somente com dados descartáveis.
- [ ] JOW-43 — preparação de edição seletiva de etiquetas: W9; editor completo não está demonstrado.
- [ ] JOW-44 — envio de faixas e álbuns: M1–M3.
- [ ] JOW-47 — desempenho: W10; consultar `arquitetura-benchmark-workspace.md` e validar limites oficiais.

## Build offline

Em uma cópia de trabalho isolada, com espaço suficiente e sem aplicativo aberto a partir do destino, use os scripts com `-Offline`. Windows precisa de `.venv` com requisitos e PyInstaller, além de FFmpeg no PATH; o script executa a suíte e substitui `dist\ytDown`. Android precisa do wrapper Gradle 8.9 e dependências já em cache, JDK 17 e SDK em `%LOCALAPPDATA%\Android`; o script roda testes e `assembleDebug` e substitui o APK no destino. `-Offline` não instala dependências nem busca artefatos remotos; cache insuficiente deve falhar. Preserve artefatos anteriores construindo em cópia isolada. A licença e a origem do FFmpeg devem acompanhar qualquer distribuição; avisos de licença ausente bloqueiam distribuição até resolução.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -Offline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_android.ps1 -Offline
Get-FileHash dist\ytDown\ytDown.exe, dist\ytDown-celular.apk -Algorithm SHA256
```

O hash do exe não identifica os demais arquivos da pasta; arquive e identifique também o pacote completo. Não publique nem crie release como parte deste roteiro.
