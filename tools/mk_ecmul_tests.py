from ethereum.tools import tester2
from ethereum import opcodes
from ethereum.utils import int_to_big_endian, encode_int32, big_endian_to_int
from ethereum.tools import new_statetest_utils
import json
import py_pairing

c = tester2.Chain(env='metropolis')
c.head_state.gas_limit = 10**8

kode = """
h: bytes32

def foo(x: bytes <= 192) -> bytes <= 64:
    o = raw_call(0x0000000000000000000000000000000000000007, x, gas=99999999, outsize=64)
    self.h = sha3(o)
    return o
"""

x1 = c.contract(kode, language='viper')

def mk_ecmul_data(p1, m):
    if isinstance(p1[0], py_pairing.FQ):
        p1 = py_pairing.normalize(p1)
        p1 = (p1[0].n, p1[1].n)
    return encode_int32(p1[0]) + encode_int32(p1[1]) + encode_int32(m)

def intrinsic_gas_of_data(d):
    return opcodes.GTXDATAZERO * d.count(0) + opcodes.GTXDATANONZERO * (len(d) - d.count(0))

def mk_test(p1, m, execgas, datarestrict=96):
    encoded = mk_ecmul_data(p1, m)[:datarestrict] + b'\x00' * max(datarestrict - 96, 0)
    pre = tester2.mk_state_test_prefill(c)
    o = x1.foo(encoded, startgas=21000 + intrinsic_gas_of_data(x1.translator.encode('foo', [encoded])) + execgas)
    if o is False:
        print('OOG %r %d %d %d' % (p1, m, datarestrict, execgas))
    else:
        x, y = big_endian_to_int(o[:32]), big_endian_to_int(o[32:])
        print('m', p1, m, py_pairing.multiply(p1, m))
        if py_pairing.normalize(py_pairing.multiply(p1, m)) != (py_pairing.FQ(x), py_pairing.FQ(y)):
            raise Exception("Mismatch! %r %r %d, expected %r computed %r" %
                            (p1, m, datarestrict, py_pairing.normalize(py_pairing.multiply(p1, m)), (x, y)))
        print('Succeeded! %r %d %d %r' % (p1, m, datarestrict, (x, y)))
    o = tester2.mk_state_test_postfill(c, pre)
    assert new_statetest_utils.verify_state_test(o)
    return o


zero = (py_pairing.FQ(1), py_pairing.FQ(1), py_pairing.FQ(0))

wrong1 = (py_pairing.FQ(1), py_pairing.FQ(3), py_pairing.FQ(1))
wrong2 = (py_pairing.FQ(0), py_pairing.FQ(3), py_pairing.FQ(1))

gaslimits = [21000, 28000]
mults = [0, 1, 2, 9, 2**128, py_pairing.curve_order - 1, py_pairing.curve_order, 2**256 - 1]
pts = [zero, py_pairing.G1, py_pairing.multiply(py_pairing.G1, 98723629835235), wrong1, wrong2]

tests = []
for g in gaslimits:
    for m in mults:
        for pt in pts:
            tests.append((pt, m, g, 96))
            tests.append((pt, m, g, 128))
            if m == 0:
                tests.append((pt, m, g, 64))
            if not m % 2**128:
                tests.append((pt, m, g, 80))
            if m == 0 and pt == zero:
                tests.append((pt, m, g, 0))
                tests.append((pt, m, g, 40))

testout = {}

for test in tests:
    testout["ecadd_%r_%r_%d_%d" % test] = mk_test(*test)
open('ecmul_tests.json', 'w').write(json.dumps(testout, indent=4))