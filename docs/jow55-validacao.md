# JOW55 — validação física

Data: 11/11/2026. Resultado: **parcial**, com transferências e recuperação do servidor comprovadas; não foi exercitada uma queda da rede do aparelho nem demonstrada uma fila de cinco pedidos simultaneamente pendentes.

Checkout `8d95dfe7a4be74148d0d10e691f2969bb6414692` (árvore limpa no início). Servidor executado diretamente com Python da `.venv` e componentes reais `SharingSession` e `LocalShareServer` desse checkout; `FakeDevices` isolou a identidade e os pareamentos de teste. Não foi usado o executável Windows. O servidor temporário foi encerrado ao fim. A descoberta automática não foi comprovada: conexão manual na LAN.

Android: aparelho ADB `[identificador omitido]`, modelo [modelo omitido], tela desbloqueada. `assembleDebug --offline` passou. O APK produzido, `android/app/build/outputs/apk/debug/app-debug.apk`, SHA-256 `BE689A5A1BF8F9F16E9F644DA21C7DC7DD455E55BFDE334AD1A0E4A2A8B11A11`, era byte a byte igual ao APK instalado. Certificados SHA-256 iguais: `[certificado omitido]`. Não houve reinstalação, desinstalação nem limpeza de dados.

Foram gerados cinco WAV sintéticos identificados por `jow55-226a7f72`, cada um com título, artista, álbum, número e capa JPEG próprios. A navegação até busca, conexão manual, pareamento por código, exibição dos cinco itens na grade e downloads na ordem 00, 01, 02, 03, 04 foram exercitados no aparelho por ADB e UI Automator via `exec-out`. Cada item chegou a “Sincronizado” antes de solicitar o próximo: isso comprova a sequência, mas não a ordenação de solicitações concorrentes ou o estado visual de fila/progresso. A presença e integridade das capas nos arquivos foi verificada; sua aparência visual na grade não foi avaliada separadamente.

Após encerramento forçado e reabertura do aplicativo, apareceu “Escolha o PC”; após nova conexão manual, o pareamento foi reutilizado e os cinco itens apareceram sincronizados. A parada do servidor produziu “Sem conexão”; ao reiniciá-lo na mesma porta, o catálogo reapareceu sem navegar. Depois o servidor foi encerrado. Não foi desligado Wi-Fi nem simulada mudança de endereço; encerramento do processo Android foi exercitado apenas após as transferências.

Os cinco arquivos recebidos foram copiados por `adb pull` exclusivamente da pasta de teste para uma pasta temporária do PC. Tamanho e SHA-256 de cada cópia coincidiram com o original; Mutagen confirmou título `JOW55 Faixa NN`, artista `JOW55 Artista NN`, álbum `JOW55 Album NN`, faixa 1–5 e uma capa APIC JPEG em cada arquivo. Os hashes das capas são distintos.

| Faixa | Bytes | SHA-256 do arquivo recebido e original |
| --- | ---: | --- |
| 00 | 35642 | `1c0d702cd8f7f1080bc3baf1867f2887568193729e36a7900c6d17f84cb98a83` |
| 01 | 51612 | `853c14572650f4f389a79ef5ff9e9cac45ec4749e84595b95b1fd1aa41849eb6` |
| 02 | 67578 | `681da445b216adad026fbc9c280baaa2b6e4aaeecdf89866d9b79a57051ca180` |
| 03 | 83564 | `b5074ee87d838d84cdea12691d9dbf66f1b655bf5b87660e7ff39761039fb489` |
| 04 | 99558 | `a4f2d02f9e33c8504bac723122aaf62203b55f276c0976e3a412d044828f9d4e` |

Os downloads e associações dos testes permaneceram no aparelho após a validação.
