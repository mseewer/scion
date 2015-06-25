# Copyright 2015 ETH Zurich
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
:mod:`lib_packet_scion_test` --- lib.packet.scion unit tests
============================================================
"""
# Stdlib
from unittest.mock import patch, MagicMock, call

# External packages
import nose
import nose.tools as ntools

# SCION
from lib.packet.ext_hdr import ExtensionHeader
from lib.packet.opaque_field import OpaqueField
from lib.packet.path import PathBase
from lib.packet.scion import (
    get_type,
    SCIONCommonHdr, SCIONHeader, SCIONPacket, IFIDPacket, PacketType,
    CertChainRequest)
from lib.packet.scion_addr import SCIONAddr


class TestGetType(object):
    """
    Unit tests for lib.packet.scion.get_type
    """
    @patch("lib.packet.scion.PacketType", autospec=True)
    def test_in_src(self, packet_type):
        pkt = MagicMock(spec_set=['hdr'])
        pkt.hdr = MagicMock(spec_set=['src_addr'])
        pkt.hdr.src_addr = MagicMock(spec_set=['host_addr'])
        pkt.hdr.src_addr.host_addr = 'src_addr'
        packet_type.SRC = ['src_addr']
        ntools.eq_(get_type(pkt), 'src_addr')

    @patch("lib.packet.scion.PacketType", autospec=True)
    def test_in_dst(self, packet_type):
        pkt = MagicMock(spec_set=['hdr'])
        pkt.hdr = MagicMock(spec_set=['src_addr', 'dst_addr'])
        pkt.hdr.dst_addr = MagicMock(spec_set=['host_addr'])
        pkt.hdr.dst_addr.host_addr = 'dst_addr'
        packet_type.SRC = []
        packet_type.DST = ['dst_addr']
        ntools.eq_(get_type(pkt), 'dst_addr')

    @patch("lib.packet.scion.PacketType", autospec=True)
    def test_in_none(self, packet_type):
        pkt = MagicMock(spec_set=['hdr'])
        pkt.hdr = MagicMock(spec_set=['src_addr', 'dst_addr'])
        packet_type.SRC = []
        packet_type.DST = []
        ntools.eq_(get_type(pkt), packet_type.DATA)


class TestSCIONCommonHdrInit(object):
    """
    Unit tests for lib.packet.scion.SCIONCommonHdr.__init__
    """
    @patch("lib.packet.scion.HeaderBase.__init__", autospec=True)
    def test_basic(self, init):
        hdr = SCIONCommonHdr()
        init.assert_called_once_with(hdr)
        ntools.eq_(hdr.version, 0)
        ntools.eq_(hdr.src_addr_len, 0)
        ntools.eq_(hdr.dst_addr_len, 0)
        ntools.eq_(hdr.total_len, 0)
        ntools.eq_(hdr.curr_iof_p, 0)
        ntools.eq_(hdr.curr_of_p, 0)
        ntools.eq_(hdr.next_hdr, 0)
        ntools.eq_(hdr.hdr_len, 0)

    @patch("lib.packet.scion.SCIONCommonHdr.parse", autospec=True)
    def test_with_args(self, parse):
        hdr = SCIONCommonHdr('data')
        parse.assert_called_once_with(hdr, 'data')


class TestSCIONCommonHdrFromValues(object):
    """
    Unit tests for lib.packet.scion.SCIONCommonHdr.from_values
    """
    def test(self):
        # called with args (src_addr_len, dst_addr_len, next_hdr)
        hdr = SCIONCommonHdr.from_values(1, 2, 3)
        ntools.assert_is_instance(hdr, SCIONCommonHdr)
        ntools.eq_(hdr.src_addr_len, 1)
        ntools.eq_(hdr.dst_addr_len, 2)
        ntools.eq_(hdr.next_hdr, 3)
        ntools.eq_(hdr.curr_of_p, 1 + 2)
        ntools.eq_(hdr.curr_iof_p, 1 + 2)
        ntools.eq_(hdr.hdr_len, SCIONCommonHdr.LEN + 1 + 2)
        ntools.eq_(hdr.total_len, SCIONCommonHdr.LEN + 1 + 2)


class TestSCIONCommonHdrParse(object):
    """
    Unit tests for lib.packet.scion.SCIONCommonHdr.parse
    """
    def test_wrong_type(self):
        hdr = SCIONCommonHdr()
        ntools.assert_raises(AssertionError, hdr.parse, 123)

    def test_bad_length(self):
        hdr = SCIONCommonHdr()
        dlen = SCIONCommonHdr.LEN - 1
        hdr.parse(b'\x00' * dlen)
        ntools.assert_false(hdr.parsed)

    def test_full(self):
        hdr = SCIONCommonHdr()
        data = bytes.fromhex('a102 0304 05 06 07 08')
        hdr.parse(data)
        ntools.eq_(hdr.total_len, 0x0304)
        ntools.eq_(hdr.curr_iof_p, 0x05)
        ntools.eq_(hdr.curr_of_p, 0x06)
        ntools.eq_(hdr.next_hdr, 0x07)
        ntools.eq_(hdr.hdr_len, 0x08)
        types = 0xa102
        ntools.eq_(hdr.version, (types & 0xf000) >> 12)
        ntools.eq_(hdr.src_addr_len, (types & 0x0fc0) >> 6)
        ntools.eq_(hdr.dst_addr_len, types & 0x003f)
        ntools.assert_true(hdr.parsed)


class TestSCIONCommonHdrPack(object):
    """
    Unit tests for lib.packet.scion.SCIONCommonHdr.pack
    """
    def test(self):
        hdr = SCIONCommonHdr()
        hdr.version = 0xa
        hdr.dst_addr_len = 0x2
        hdr.src_addr_len = 0x4
        hdr.total_len = 0x304
        hdr.curr_iof_p = 0x5
        hdr.curr_of_p = 0x6
        hdr.next_hdr = 0x7
        hdr.hdr_len = 0x8
        packed = bytes.fromhex('a102 0304 05 06 07 08')
        ntools.eq_(hdr.pack(), packed)


class TestSCIONHeaderInit(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.__init__
    """
    @patch("lib.packet.scion.HeaderBase.__init__", autospec=True)
    def test_basic(self, init):
        hdr = SCIONHeader()
        init.assert_called_once_with(hdr)
        ntools.assert_is_none(hdr.common_hdr)
        ntools.assert_is_none(hdr.src_addr)
        ntools.assert_is_none(hdr.dst_addr)
        ntools.assert_is_none(hdr._path)
        ntools.eq_(hdr._extension_hdrs, [])

    @patch("lib.packet.scion.SCIONHeader.parse", autospec=True)
    def test_with_args(self, parse):
        hdr = SCIONHeader('data')
        parse.assert_called_once_with(hdr, 'data')


class TestSCIONHeaderFromValues(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.from_values
    """
    def test_bad_src(self):
        dst = MagicMock(spec_set=SCIONAddr)
        ntools.assert_raises(AssertionError, SCIONHeader.from_values, 'src',
                             dst)

    def test_bad_dst(self):
        src = MagicMock(spec_set=SCIONAddr)
        ntools.assert_raises(AssertionError, SCIONHeader.from_values, src,
                             'dst')

    def test_bad_path(self):
        src = MagicMock(spec_set=SCIONAddr)
        dst = MagicMock(spec_set=SCIONAddr)
        ntools.assert_raises(AssertionError, SCIONHeader.from_values, src,
                             dst, path='path')

    @patch("lib.packet.scion.SCIONHeader.set_ext_hdrs", autospec=True)
    @patch("lib.packet.scion.SCIONHeader.set_path", autospec=True)
    @patch("lib.packet.scion.SCIONCommonHdr.from_values",
           spec_set=SCIONCommonHdr.from_values)
    def test_full(self, scion_common_hdr, set_path, set_ext_hdrs):
        src = MagicMock(spec_set=['addr_len', '__class__'])
        dst = MagicMock(spec_set=['addr_len', '__class__'])
        dst.__class__ = src.__class__ = SCIONAddr
        path = MagicMock(spec_set=PathBase)
        ext_hdrs = 'ext_hdrs'
        next_hdr = 100
        scion_common_hdr.return_value = 'scion_common_hdr'
        hdr = SCIONHeader.from_values(src, dst, path, ext_hdrs, next_hdr)
        ntools.assert_is_instance(hdr, SCIONHeader)
        scion_common_hdr.assert_called_once_with(src.addr_len, dst.addr_len,
                                                 next_hdr)
        ntools.eq_(hdr.common_hdr, 'scion_common_hdr')
        ntools.eq_(hdr.src_addr, src)
        ntools.eq_(hdr.dst_addr, dst)
        set_path.assert_called_once_with(hdr, path)
        set_ext_hdrs.assert_called_once_with(hdr, ext_hdrs)


class TestSCIONHeaderPath(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.path
    """
    def test_getter(self):
        hdr = SCIONHeader()
        hdr._path = 'path'
        ntools.eq_(hdr.path, 'path')

    @patch("lib.packet.scion.SCIONHeader.set_path", autospec=True)
    def test_setter(self, set_path):
        hdr = SCIONHeader()
        hdr.path = 'path'
        set_path.assert_called_once_with(hdr, 'path')


class TestSCIONHeaderSetPath(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.set_path
    """
    def test_with_none(self):
        hdr = SCIONHeader()
        hdr._path = MagicMock(spec_set=['pack'])
        hdr._path.pack.return_value = b'old_path'
        hdr.common_hdr = MagicMock(spec_set=['hdr_len', 'total_len'])
        hdr.common_hdr.hdr_len = 100
        hdr.common_hdr.total_len = 200
        hdr.set_path(None)
        ntools.eq_(hdr.common_hdr.hdr_len, 100 - len(b'old_path'))
        ntools.eq_(hdr.common_hdr.total_len, 200 - len(b'old_path'))
        ntools.assert_is_none(hdr._path)

    def test_not_none(self):
        hdr = SCIONHeader()
        hdr._path = MagicMock(spec_set=['pack'])
        hdr._path.pack.return_value = b'old_path'
        hdr.common_hdr = MagicMock(spec_set=['hdr_len', 'total_len'])
        hdr.common_hdr.hdr_len = 100
        hdr.common_hdr.total_len = 200
        path = MagicMock(spec_set=['pack'])
        path.pack.return_value = b'packed_path'
        hdr.set_path(path)
        ntools.eq_(hdr._path, path)
        ntools.eq_(hdr.common_hdr.hdr_len,
                   100 - len(b'old_path') + len(b'packed_path'))
        ntools.eq_(hdr.common_hdr.total_len,
                   200 - len(b'old_path') + len(b'packed_path'))


class TestSCIONHeaderExtensionHdrs(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.extension_hdrs
    """
    def test_getter(self):
        hdr = SCIONHeader()
        hdr._extension_hdrs = 'ext_hdrs'
        ntools.eq_(hdr.extension_hdrs, 'ext_hdrs')

    @patch("lib.packet.scion.SCIONHeader.set_ext_hdrs", autospec=True)
    def test_setter(self, set_ext_hdrs):
        hdr = SCIONHeader()
        hdr.extension_hdrs = 'ext_hdrs'
        set_ext_hdrs.assert_called_once_with(hdr, 'ext_hdrs')


class TestSCIONHeaderSetExtHdrs(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.set_path
    """
    def test_bad_type(self):
        hdr = SCIONHeader()
        ntools.assert_raises(AssertionError, hdr.set_ext_hdrs, 123)

    @patch("lib.packet.scion.SCIONHeader.append_ext_hdr", autospec=True)
    @patch("lib.packet.scion.SCIONHeader.pop_ext_hdr", autospec=True)
    def test_full(self, pop, append):
        hdr = SCIONHeader()
        ext_hdrs = ['ext_hdr0', 'ext_hdr1']
        # hdr._extension_hdrs = ['old_ext_hdr' + str(i) for i in range(3)]
        # FIXME: pop_ext_hdr side effect should 'pop' hdr._extension_hdrs
        hdr.set_ext_hdrs(ext_hdrs)
        # pop.assert_has_calls([call()] * 3)
        append.assert_has_calls([call(hdr, 'ext_hdr0'), call(hdr, 'ext_hdr1')])


class TestSCIONHeaderAppendExtHdr(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.append_ext_hdr
    """
    def test_bad_type(self):
        hdr = SCIONHeader()
        ntools.assert_raises(AssertionError, hdr.append_ext_hdr, 123)

    def test_full(self):
        hdr = SCIONHeader()
        hdr._extension_hdrs = []
        hdr.common_hdr = MagicMock(spec_set=['total_len'])
        hdr.common_hdr.total_len = 0
        ext_hdr = MagicMock(spec_set=ExtensionHeader)
        ext_hdr.__len__.return_value = 123
        hdr.append_ext_hdr(ext_hdr)
        ntools.assert_in(ext_hdr, hdr._extension_hdrs)
        ntools.eq_(hdr.common_hdr.total_len, 123)


class TestSCIONHeaderPopExtHdr(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.pop_ext_hdr
    """
    def test_none(self):
        hdr = SCIONHeader()
        hdr._extension_hdrs = []
        ntools.assert_is_none(hdr.pop_ext_hdr())

    def test_full(self):
        hdr = SCIONHeader()
        hdr._extension_hdrs = ['ext_hdr0', 'ext_hdr1']
        hdr.common_hdr = MagicMock(spec_set=['total_len'])
        hdr.common_hdr.total_len = 10
        ntools.eq_(hdr.pop_ext_hdr(), 'ext_hdr1')
        ntools.eq_(hdr._extension_hdrs, ['ext_hdr0'])
        ntools.eq_(hdr.common_hdr.total_len, 10 - len('ext_hdr1'))


class TestSCIONHeaderParse(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.parse
    """
    def test(self):
        # TODO: refactor code
        pass


class TestSCIONHeaderPack(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.pack
    """
    def _check(self, path, packed_path):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['pack'])
        hdr.common_hdr.pack.return_value = b'common_hdr'
        hdr.src_addr= MagicMock(spec_set=['pack'])
        hdr.src_addr.pack.return_value = b'src_addr'
        hdr.dst_addr = MagicMock(spec_set=['pack'])
        hdr.dst_addr.pack.return_value = b'dst_addr'
        hdr._path = path
        hdr._extension_hdrs = [MagicMock(spec_set=['pack']) for i in range(2)]
        for i, ext_hdr in enumerate(hdr._extension_hdrs):
            ext_hdr.pack.return_value = b'ext_hdr' + str.encode(str(i))
        packed = b'common_hdrsrc_addrdst_addr'+ packed_path + \
                 b'ext_hdr0ext_hdr1'
        ntools.eq_(hdr.pack(), packed)

    def test(self):
        paths = [None, MagicMock(spec_set=['pack'])]
        paths[1].pack.return_value = b'path'
        packed_paths = [b'', b'path']
        for path, packed_path in zip(paths, packed_paths):
            yield self._check, path, packed_path


class TestSCIONHeaderGetCurrentOf(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.get_current_of
    """
    def test_none(self):
        hdr = SCIONHeader()
        ntools.assert_is_none(hdr.get_current_of())

    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'src_addr_len',
                                             'dst_addr_len'])
        hdr.common_hdr.curr_of_p = 123
        hdr.common_hdr.src_addr_len = 456
        hdr.common_hdr.dst_addr_len = 789
        hdr._path = MagicMock(spec_set=['get_of'])
        hdr._path.get_of.return_value = 'get_current_of'
        offset = 123 - (456 + 789)
        ntools.eq_(hdr.get_current_of(), 'get_current_of')
        hdr._path.get_of.assert_called_once_with(offset // OpaqueField.LEN)


class TestSCIONHeaderGetCurrentIof(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.get_current_iof
    """
    def test_none(self):
        hdr = SCIONHeader()
        ntools.assert_is_none(hdr.get_current_iof())

    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['curr_iof_p', 'src_addr_len',
                                             'dst_addr_len'])
        hdr.common_hdr.curr_iof_p = 123
        hdr.common_hdr.src_addr_len = 456
        hdr.common_hdr.dst_addr_len = 789
        hdr._path = MagicMock(spec_set=['get_of'])
        hdr._path.get_of.return_value = 'get_current_iof'
        offset = 123 - (456 + 789)
        ntools.eq_(hdr.get_current_iof(), 'get_current_iof')
        hdr._path.get_of.assert_called_once_with(offset // OpaqueField.LEN)


class TestSCIONHeaderGetRelativeOf(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.get_relative_of
    """
    def test_none(self):
        hdr = SCIONHeader()
        ntools.assert_is_none(hdr.get_relative_of(123))

    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'src_addr_len',
                                             'dst_addr_len'])
        hdr.common_hdr.curr_of_p = 123
        hdr.common_hdr.src_addr_len = 456
        hdr.common_hdr.dst_addr_len = 789
        hdr._path = MagicMock(spec_set=['get_of'])
        hdr._path.get_of.return_value = 'get_relative_of'
        offset = 123 - (456 + 789)
        ntools.eq_(hdr.get_relative_of(321), 'get_relative_of')
        hdr._path.get_of.assert_called_once_with(offset // OpaqueField.LEN +
                                                 321)


class TestSCIONHeaderGetNextOf(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.get_next_of
    """
    def test_none(self):
        hdr = SCIONHeader()
        ntools.assert_is_none(hdr.get_next_of())

    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'src_addr_len',
                                             'dst_addr_len'])
        hdr.common_hdr.curr_of_p = 123
        hdr.common_hdr.src_addr_len = 456
        hdr.common_hdr.dst_addr_len = 789
        hdr._path = MagicMock(spec_set=['get_of'])
        hdr._path.get_of.return_value = 'get_next_of'
        offset = 123 - (456 + 789)
        ntools.eq_(hdr.get_next_of(), 'get_next_of')
        hdr._path.get_of.assert_called_once_with(offset // OpaqueField.LEN + 1)


class TestSCIONHeaderIncreaseOf(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.increase_of
    """
    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p'])
        hdr.common_hdr.curr_of_p = 0
        hdr.increase_of(123)
        ntools.eq_(hdr.common_hdr.curr_of_p, 123 * OpaqueField.LEN)


class TestSCIONHeaderSetDownpath(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.set_downpath
    """
    @patch("lib.packet.scion.SCIONHeader.get_current_iof", autospec=True)
    def test_iof_none(self, get_current_iof):
        hdr = SCIONHeader()
        get_current_iof.return_value = None
        hdr.set_downpath()
        get_current_iof.assert_called_once_with(hdr)

    @patch("lib.packet.scion.SCIONHeader.get_current_iof", autospec=True)
    def test_with_iof(self, get_current_iof):
        hdr = SCIONHeader()
        iof = MagicMock(spec_set=['up_flag'])
        get_current_iof.return_value = iof
        hdr.set_downpath()
        ntools.assert_false(iof.up_flag)


class TestSCIONHeaderIsOnUpPath(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.is_on_up_path
    """
    @patch("lib.packet.scion.SCIONHeader.get_current_iof", autospec=True)
    def test_iof_none(self, get_current_iof):
        hdr = SCIONHeader()
        get_current_iof.return_value = None
        ntools.assert_true(hdr.is_on_up_path())
        get_current_iof.assert_called_once_with(hdr)

    @patch("lib.packet.scion.SCIONHeader.get_current_iof", autospec=True)
    def test_with_iof(self, get_current_iof):
        hdr = SCIONHeader()
        iof = MagicMock(spec_set=['up_flag'])
        get_current_iof.return_value = iof
        ntools.eq_(hdr.is_on_up_path(), iof.up_flag)


class TestSCIONHeaderIsLastPathOf(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.is_last_path_of
    """
    def test_true(self):
        hdr = SCIONHeader()
        offset = (SCIONCommonHdr.LEN + OpaqueField.LEN)
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'hdr_len'])
        hdr.common_hdr.curr_of_p = 123
        hdr.common_hdr.hdr_len = 123 + offset
        ntools.assert_true(hdr.is_last_path_of())

    def test_false(self):
        hdr = SCIONHeader()
        offset = (SCIONCommonHdr.LEN + OpaqueField.LEN)
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'hdr_len'])
        hdr.common_hdr.curr_of_p = 123
        hdr.common_hdr.hdr_len = 456 + offset
        ntools.assert_false(hdr.is_last_path_of())


class TestSCIONHeaderReverse(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.reverse
    """
    def test(self):
        hdr = SCIONHeader()
        hdr.src_addr = 'src_addr'
        hdr.dst_addr = 'dst_addr'
        hdr._path = MagicMock(spec_set=['reverse'])
        hdr.common_hdr = MagicMock(spec_set=['curr_of_p', 'curr_iof_p',
                                             'src_addr_len', 'dst_addr_len'])
        hdr.common_hdr.src_addr_len = 123
        hdr.common_hdr.dst_addr_len = 456
        hdr.reverse()
        ntools.eq_(hdr.src_addr, 'dst_addr')
        ntools.eq_(hdr.dst_addr, 'src_addr')
        hdr._path.reverse.assert_called_once_with()
        ntools.eq_(hdr.common_hdr.curr_of_p, 123 + 456)
        ntools.eq_(hdr.common_hdr.curr_iof_p, 123 + 456)


class TestSCIONHeaderLen(object):
    """
    Unit tests for lib.packet.scion.SCIONHeader.__len__
    """
    def test(self):
        hdr = SCIONHeader()
        hdr.common_hdr = MagicMock(spec_set=['hdr_len'])
        hdr.common_hdr.hdr_len = 123
        hdr._extension_hdrs = ['ext_hdr0', 'ext_hdr01']
        ntools.eq_(len(hdr), 123 + len('ext_hdr0') + len('ext_hdr01'))


class TestSCIONPacketInit(object):
    """
    Unit tests for lib.packet.scion.SCIONPacket.__init__
    """
    @patch("lib.packet.scion.PacketBase.__init__", autospec=True)
    def test_basic(self, init):
        packet = SCIONPacket()
        init.assert_called_once_with(packet)
        ntools.eq_(packet.payload_len, 0)

    @patch("lib.packet.scion.SCIONPacket.parse", autospec=True)
    def test_with_args(self, parse):
        packet = SCIONPacket('data')
        parse.assert_called_once_with(packet, 'data')


class TestSCIONPacketFromValues(object):
    """
    Unit tests for lib.packet.scion.SCIONPacket.from_values
    """
    @patch("lib.packet.scion.SCIONPacket.set_hdr", autospec=True)
    @patch("lib.packet.scion.SCIONPacket.set_payload", autospec=True)
    @patch("lib.packet.scion.SCIONHeader.from_values",
           spec_set=SCIONHeader.from_values)
    def test_basic(self, scion_hdr, set_payload, set_hdr):
        scion_hdr.return_value = 'hdr'
        packet = SCIONPacket.from_values('src', 'dst', 'payload', 'path',
                                         'ext_hdrs', 'next_hdr')
        ntools.assert_is_instance(packet, SCIONPacket)
        scion_hdr.assert_called_once_with('src', 'dst', 'path', 'ext_hdrs',
                                          'next_hdr')
        set_hdr.assert_called_once_with(packet, 'hdr')
        set_payload.assert_called_once_with(packet, 'payload')

    @patch("lib.packet.scion.SCIONPacket.set_hdr", autospec=True)
    @patch("lib.packet.scion.SCIONPacket.set_payload", autospec=True)
    @patch("lib.packet.scion.SCIONHeader.from_values",
           spec_set=SCIONHeader.from_values)
    def test_less_args(self, scion_hdr, set_payload, set_hdr):
        packet = SCIONPacket.from_values('src', 'dst', 'payload')
        scion_hdr.assert_called_once_with('src', 'dst', None, None, 0)


class TestSCIONPacketSetPayload(object):
    """
    Unit tests for lib.packet.scion.SCIONPacket.set_payload
    """
    @patch("lib.packet.scion.PacketBase.set_payload", autospec=True)
    def test(self, set_payload):
        packet = SCIONPacket()
        packet.payload_len = 123
        packet._hdr = MagicMock(spec_set=['common_hdr'])
        packet._hdr.common_hdr = MagicMock(spec_set=['total_len'])
        packet._hdr.common_hdr.total_len = 456
        packet.set_payload('payload')
        set_payload.assert_called_once_with(packet, 'payload')
        ntools.eq_(packet.payload_len, len('payload'))
        ntools.eq_(packet.hdr.common_hdr.total_len, 456 - 123 + len('payload'))


class TestSCIONPacketParse(object):
    """
    Unit tests for lib.packet.scion.SCIONPacket.parse
    """
    def test_bad_type(self):
        packet = SCIONPacket()
        ntools.assert_raises(AssertionError, packet.parse, 123)

    def test_bad_length(self):
        packet = SCIONPacket()
        data = b'\x00' * (SCIONPacket.MIN_LEN - 1)
        packet.parse(data)
        ntools.assert_false(packet.parsed)

    @patch("lib.packet.scion.SCIONPacket.set_payload", autospec=True)
    @patch("lib.packet.scion.SCIONPacket.set_hdr", autospec=True)
    @patch("lib.packet.scion.SCIONHeader", autospec=True)
    def test_full(self, scion_hdr, set_hdr, set_payload):
        packet = SCIONPacket()
        packet._hdr = 'header'
        data = bytes(range(SCIONPacket.MIN_LEN))
        scion_hdr.return_value = 'scion_header'
        packet.parse(data)
        ntools.eq_(packet.raw, data)
        scion_hdr.assert_called_once_with(data)
        set_hdr.assert_called_once_with(packet, 'scion_header')
        hdr_len = len(packet.hdr)
        ntools.eq_(packet.payload_len, len(data) - hdr_len)
        set_payload.assert_called_once_with(packet, data[hdr_len:])
        ntools.assert_true(packet.parsed)


class TestSCIONPacketPack(object):
    """
    Unit tests for lib.packet.scion.SCIONPacket.pack
    """
    def test_payload_packetbase(self):
        packet = SCIONPacket()
        packet._hdr = MagicMock(spec_set=['pack'])
        packet._hdr.pack.return_value = b'packed_hdr'
        packet._payload = MagicMock(spec_set=SCIONPacket)
        packet._payload.pack.return_value = b'packed_payload'
        ntools.eq_(packet.pack(), b'packed_hdrpacked_payload')

    def test_payload_packetbase(self):
        packet = SCIONPacket()
        packet._hdr = MagicMock(spec_set=['pack'])
        packet._hdr.pack.return_value = b'packed_hdr'
        packet._payload = b'packed_payload'
        ntools.eq_(packet.pack(), b'packed_hdrpacked_payload')


class TestIFIDPacketInit(object):
    """
    Unit tests for lib.packet.scion.IFIDPacket.__init__
    """
    @patch("lib.packet.scion.SCIONPacket.__init__", autospec=True)
    def test_basic(self, init):
        packet = IFIDPacket()
        init.assert_called_once_with(packet)
        ntools.eq_(packet.reply_id, 0)
        ntools.assert_is_none(packet.request_id)

    @patch("lib.packet.scion.IFIDPacket.parse", autospec=True)
    def test_with_args(self, parse):
        packet = IFIDPacket('data')
        parse.assert_called_once_with(packet, 'data')


class TestIFIDPacketParse(object):
    """
    Unit tests for lib.packet.scion.IFIDPacket.parse
    """
    @patch("lib.packet.scion.SCIONPacket.parse", autospec=True)
    def test(self, parse):
        packet = IFIDPacket()
        packet._payload = bytes.fromhex('0102 0304')
        packet.parse('data')
        parse.assert_called_once_with(packet, 'data')
        ntools.eq_(packet.reply_id, 0x102)
        ntools.eq_(packet.request_id, 0x304)


class TestIFIDPacketFromValues(object):
    """
    Unit tests for lib.packet.scion.IFIDPacket.from_values
    """
    @patch("lib.packet.scion.IFIDPacket.set_payload", autospec=True)
    @patch("lib.packet.scion.IFIDPacket.set_hdr", autospec=True)
    @patch("lib.packet.scion.SCIONHeader.from_values",
           spec_set=SCIONHeader.from_values)
    @patch("lib.packet.scion.SCIONAddr.from_values",
           spec_set=SCIONAddr.from_values)
    def test(self, scion_addr, scion_hdr, set_hdr, set_payload):
        scion_addr.return_value = 'dst'
        dst_isd_ad = MagicMock(spec_set=['isd', 'ad'])
        scion_hdr.return_value = 'hdr'
        packet = IFIDPacket.from_values('src', dst_isd_ad, 0x0102)
        ntools.assert_is_instance(packet, IFIDPacket)
        ntools.eq_(packet.request_id, 0x0102)
        scion_addr.assert_called_once_with(dst_isd_ad.isd, dst_isd_ad.ad,
                                           PacketType.IFID_PKT)
        scion_hdr.assert_called_once_with('src', 'dst')
        set_hdr.assert_called_once_with(packet, 'hdr')
        set_payload.assert_called_once_with(packet, bytes.fromhex('0000 0102'))


class TestIFIDPacketPack(object):
    """
    Unit tests for lib.packet.scion.IFIDPacket.pack
    """
    @patch("lib.packet.scion.SCIONPacket.pack", autospec=True)
    @patch("lib.packet.scion.IFIDPacket.set_payload", autospec=True)
    def test(self, set_payload, pack):
        packet = IFIDPacket()
        packet.reply_id = 0x0102
        packet.request_id = 0x0304
        pack.return_value = b'packed_ifid'
        ntools.eq_(packet.pack(), b'packed_ifid')
        set_payload.assert_called_once_with(packet, bytes.fromhex('0102 0304'))
        pack.assert_called_once_with(packet)


if __name__ == "__main__":
    nose.run(defaultTest=__name__)
