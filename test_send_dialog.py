"""Testa a janela de envio com uma janela Tk real, sem rede."""

import gc
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

import share
from send_dialog import SendDialog


class SendDialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        # Coleta as variáveis Tk do teste enquanto a janela ainda existe; coletadas
        # depois, em outra thread, elas imprimem erros que esconderiam problemas reais.
        self.addCleanup(gc.collect)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = mock.patch.object(share, "default_store_path", lambda: Path(temp.name) / "pairing.json")
        store.start()
        self.addCleanup(store.stop)

    def toplevels(self):
        return [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)]

    def test_no_empty_window_is_left_when_sharing_cannot_start(self):
        with mock.patch.object(share.ShareServer, "start", side_effect=share.ShareError("porta ocupada")):
            with self.assertRaises(share.ShareError):
                SendDialog(self.root, on_closed=lambda: None)
        self.root.update()
        self.assertEqual(self.toplevels(), [])

    def test_shows_code_address_and_files(self):
        closed = []
        original_start = share.ShareServer.start
        free_ports = lambda server: original_start(server, http_port=0, discovery_port=0)  # noqa: E731
        with mock.patch.object(share.ShareServer, "start", free_ports):
            dialog = SendDialog(self.root, on_closed=lambda: closed.append(True))
        self.addCleanup(lambda: closed or dialog.close())
        dialog.add(Path("a.mp3"))
        dialog.add(Path("b.mp3"))
        self.root.after(400, self.root.quit)
        self.root.mainloop()  # Deixa o laço de atualização da janela rodar.

        code = dialog.server.pairing_code
        self.assertEqual(dialog.code.get(), f"{code[:3]} {code[3:]}")
        self.assertIn(f":{dialog.server.port}", dialog.address.get())
        names = [dialog.files.item(row)["values"][0] for row in dialog.files.get_children()]
        self.assertEqual(names, ["a.mp3", "b.mp3"])

        dialog.close()
        self.assertEqual(closed, [True])
        self.assertTrue(dialog.server.stopping)


if __name__ == "__main__":
    unittest.main()
