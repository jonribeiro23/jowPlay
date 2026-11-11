# Catálogo automático na rede local

Ao abrir o aplicativo do PC, o serviço local é iniciado e disponibiliza as faixas indexadas existentes, além dos arquivos adicionados pelo envio legado. O botão **Conectar celular** exibe o código para um novo pareamento sem exigir uma faixa selecionada. Fechar essa janela não encerra o serviço; ele termina ao fechar o aplicativo.

O catálogo consulta a biblioteca novamente a cada pedido. Os identificadores das faixas permanecem no SQLite e os dispositivos pareados no registro existente. O Android procura PCs na rede e conecta automaticamente quando encontra exatamente um PC com token conhecido; se existirem vários PCs pareados, apresenta a escolha. Após mudança de endereço, procura novamente pelo mesmo identificador. Os arquivos baixados e suas associações permanecem no aparelho.

O cálculo SHA-256 ocorre em thread de serviço. Durante uma consulta demorada o servidor envia fragmentos de espera, evitando o timeout de leitura do Android; a lista completa só aparece depois da conclusão. O cache de hashes usa tamanho, data de modificação e data de alteração do sistema de arquivos (no Windows, `ChangeTime`), além do caminho. Se a data de alteração não estiver disponível, o hash é recalculado. O servidor espera as consultas terminarem antes de fechar a biblioteca. A integridade continua verificada durante o download.

O protocolo existente usa HTTP e descoberta UDP sem autenticação do servidor ou criptografia. O código e os tokens restringem o acesso, mas não protegem contra espionagem ou falsificação por alguém na mesma rede. Use somente redes confiáveis; autenticação mútua e TLS exigem evolução do protocolo e migração de pareamentos.
