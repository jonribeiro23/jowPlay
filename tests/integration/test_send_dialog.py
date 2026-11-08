"""Testa a janela de envio com uma janela Tk real; o servidor usa portas livres."""

import gc
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from tests.fakes import FakeDevices
from ytdown.application.sharing import SharingSession
from ytdown.domain.errors import ShareError
from ytdown.infrastructure.sharing.server import LocalShareServer
from ytdown.presentation.send_dialog import SendDialog


def free_port_server(on_change):
    return LocalShareServer(SharingSession(FakeDevices(), on_change), http_port=0, discovery_port=0)


class SendDialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        # Coleta as variáveis Tk do teste enquanto a janela ainda existe; coletadas
        # depois, em outra thread, elas imprimem erros que esconderiam problemas reais.
        self.addCleanup(gc.collect)

    def toplevels(self):
        return [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]

    def test_no_empty_window_is_left_when_sharing_cannot_start(self):
        with mock.patch.object(LocalShareServer, "start", side_effect=ShareError("porta ocupada")):
            with self.assertRaises(ShareError):
                SendDialog(self.root, free_port_server, on_closed=lambda: None)
        self.root.update()
        self.assertEqual(self.toplevels(), [])

    def test_shows_code_address_and_files(self):
        closed = []
        dialog = SendDialog(self.root, free_port_server, on_closed=lambda: closed.append(True))
        self.addCleanup(lambda: closed or dialog.close())
        dialog.add(Path("a.mp3"))
        dialog.add(Path("b.mp3"))
        self.root.after(400, self.root.quit)
        self.root.mainloop()  # Deixa o laço de atualização da janela rodar.

        code = dialog.server.pairing_code
        self.assertEqual(dialog.code.get(), f"{code[:3]} {code[3:]}")
        self.assertIn(f":{dialog.server.port}", dialog.address.get())
        rows = [dialog.files.item(row)["values"] for row in dialog.files.get_children()]
        self.assertEqual(rows, [["a.mp3", "Aguardando o celular"], ["b.mp3", "Aguardando o celular"]])

        dialog.close()
        self.assertEqual(closed, [True])
        self.assertTrue(dialog.server.stopping)


if __name__ == "__main__":
    unittest.main()
