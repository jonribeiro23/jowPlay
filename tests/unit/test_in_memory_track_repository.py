"""O repositório em memória dos testes também cumpre o contrato, então os testes de
casos de uso que o usam valem para qualquer implementação real.
"""

import unittest

from tests.contracts.track_repository import TrackRepositoryContract
from tests.fakes import InMemoryTrackRepository


class InMemoryTrackRepositoryTests(TrackRepositoryContract, unittest.TestCase):
    def make_repository(self):
        return InMemoryTrackRepository()


if __name__ == "__main__":
    unittest.main()
