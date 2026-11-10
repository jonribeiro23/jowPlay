# Controles da miniatura do Windows

Os controles dependem do Explorer, de uma janela com botão na barra e de miniaturas habilitadas. A barra pode truncar botões quando há pouco espaço. A integração aguarda `TaskbarButtonCreated` e recria a interface COM e os botões quando a mensagem volta a chegar após reinício do Explorer. Falhas são registradas no log e não devem interromper a reprodução.

Referências: [ThumbBarAddButtons](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-itaskbarlist3-thumbbaraddbuttons) e [Taskbar Extensions](https://learn.microsoft.com/en-us/windows/win32/shell/taskbar-extensions).

Teste parcial no Windows com Qt offscreen: criação dos quatro ícones, conexão COM e liberação. Validação manual pendente: miniatura e cliques no Explorer, mudanças reais de estado, reinício do Explorer, DPI e ciclo de fechamento. O executável empacotado não foi testado.
