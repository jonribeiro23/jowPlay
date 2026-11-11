# JOW54 — galeria Android

A tela de arquivos usa grade adaptável, capa quadrada com estado sobre a borda inferior e título e artista abaixo. A capa solicita a fila existente; itens sincronizados, na fila ou ativos não aceitam novo toque. O ViewModel também recusa solicitações de itens sincronizados e versões antigas. Falhas podem ser repetidas pela capa quando conectada. A atualização periódica do catálogo e da conexão permanece na tela.

Validação em 11/11/2026: `testDebugUnitTest assembleDebug assembleDebugAndroidTest` passaram; o teste unitário adicional verifica rejeição de item sincronizado e versão antiga. APK debug instalado com `adb install -r` no aparelho [modelo omitido] após comparar SHA-256 dos certificados (idênticos).

O servidor real do projeto foi iniciado temporariamente com identidade exclusiva `jow54-078c99f0`, 18 arquivos WAV sintéticos e capas geradas; conexão manual pela rede privada, sem descoberta. O cliente não permite loopback, portanto não foi usado `adb reverse`. Foram verificados a grade, imagens e alternativa sem capa, título longo, toque e estado Sincronizado, rolagem até a faixa 17, desconexão e reconexão sem navegar. As capturas e árvores de acessibilidade foram analisadas durante o teste. A automação é `scripts/jow54_device_check.py` (definir `PYTHONPATH` para a raiz do projeto).

Dois testes instrumentados existentes de MediaStore passaram no dispositivo (2/2); são testes de armazenamento, não testes instrumentados de UI Compose. A interface foi exercitada por ADB/UI Automator, não por uma suíte Compose instrumentada. Os estados visuais de fila, progresso e falha não foram capturados: o arquivo de teste terminou rapidamente.
