import pytest
from kalkulacka import secti, odecti, vynasob, vydel


def test_secti():
    assert secti(2, 3) == 5
    assert secti(-1, 1) == 0


def test_odecti():
    assert odecti(5, 3) == 2
    assert odecti(0, 5) == -5


def test_vynasob():
    assert vynasob(3, 4) == 12
    assert vynasob(-2, 3) == -6


def test_vydel():
    assert vydel(10, 2) == 5.0
    assert vydel(7, 2) == 3.5


def test_vydel_nulou():
    with pytest.raises(ValueError):
        vydel(5, 0)
