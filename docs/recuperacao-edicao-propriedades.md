# Recuperação após editar propriedades

Cada edição que altera um arquivo guarda uma cópia do original em
`.ytdown-recovery/edicao-.../original.ext`, dentro da pasta da biblioteca.
O arquivo `caminho-original.txt` na mesma pasta registra o caminho original,
relativo à biblioteca. Essas cópias não são apagadas automaticamente, inclusive
depois de uma edição bem-sucedida; podem ser removidas manualmente quando não
forem mais necessárias. Uma edição interrompida antes de terminar a cópia pode
deixar uma cópia incompleta; nesse caso, o arquivo original ainda não foi alterado.

O arquivo editado é preparado antes da troca ou remoção do original. Uma falha
do processo ou do computador durante a troca, a mudança de caminho ou a gravação
do banco ainda pode deixar o índice e os arquivos divergentes: não há transação
única entre o sistema de arquivos e o SQLite, nem recuperação automática na
inicialização. Para recuperar, feche o aplicativo, localize a pasta de recuperação
da edição e seu `caminho-original.txt`, e guarde uma cópia dos arquivos atuais.
Restaure o original para o caminho indicado e confira a faixa no aplicativo;
se o índice já apontar para outro caminho, pode ser necessário reimportar a faixa
ou restaurar também um backup do banco. Não sobrescreva arquivos de outra faixa.

Quando a edição falha e a restauração automática também falha, a mensagem informa
o caminho da cópia de recuperação. No Windows, um arquivo aberto sem permissão de
compartilhar exclusão pode impedir a troca: a edição daquela faixa falha e o lote
continua com as demais.
