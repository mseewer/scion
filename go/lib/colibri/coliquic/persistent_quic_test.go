// Copyright 2022 ETH Zurich
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//   http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package coliquic

import (
	"crypto/tls"
	"errors"
	"net"
	"sync"
	"testing"
	"time"

	"github.com/lucas-clemente/quic-go"
	"github.com/stretchr/testify/require"
	"golang.org/x/net/context"
)

func TestInvariantColibriRepresentation(t *testing.T) {
	colPath := newTestColibriPath()
	copy(colPath.PacketTimestamp[:], []byte{0, 1, 2, 3, 4, 5, 6, 7})
	colPath.InfoField.OrigPayLen = 12345
	buff := make([]byte, colPath.Len())
	err := colPath.SerializeTo(buff)
	require.NoError(t, err)

	// representation of the original
	repr1 := invariantColibri(buff)

	// modify timestamp and orig payload length and obtain the representation again
	copy(colPath.PacketTimestamp[:], []byte{10, 11, 12, 13, 14, 15, 16, 17})
	colPath.InfoField.OrigPayLen = 11111
	err = colPath.SerializeTo(buff)
	require.NoError(t, err)
	repr2 := invariantColibri(buff)

	require.Equal(t, repr1, repr2)
}

// TestSingleSession checks that only one session is created per path.
func TestReuseSession(t *testing.T) {
	t.Skip("reenable this test")
	// mimic the tiny topology, and attempt to connect from 111 to 110 and 112, using
	// both regular SCION and COLIBRI paths
	// deleteme XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX change timeout below
	ctx, cancelF := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelF()
	thisNet := newMockNetwork(t)
	clientAddr := mockScionAddress(t, "1-ff00:0:111", "127.0.0.1:12345")
	pconn := newConnMock(t, clientAddr, thisNet)
	clientTlsConfig := &tls.Config{
		InsecureSkipVerify: true,
		NextProtos:         []string{"coliquictest"},
	}

	dialer := NewPersistentQUIC(pconn, clientTlsConfig, nil)
	require.Len(t, dialer.sessions, 0)

	serverWg := sync.WaitGroup{}
	clientWg := sync.WaitGroup{}
	messages := make(chan string)
	runServer := func(serverAddr net.Addr, msg string) {
		serverWg.Add(1)
		go func() {
			defer serverWg.Done()
			serverTlsConfig := &tls.Config{
				Certificates: []tls.Certificate{*createTestCertificate(t)},
				NextProtos:   []string{"coliquictest"},
			}
			serverQuicConfig := &quic.Config{KeepAlive: true}
			listener, err := quic.Listen(newConnMock(t, serverAddr, thisNet),
				serverTlsConfig, serverQuicConfig)
			require.NoError(t, err, "failed with message %s", msg)
			session, err := listener.Accept(ctx)
			// N.B. the server blocks here because there is no client trying to open a new session, but only a new stream
			// for this to work, the server must be only waiting to open a stream if the session was already opened
			require.NoError(t, err, "failed with message %s", msg)

			t.Logf("connected  to %s", serverAddr)
			stream, err := session.AcceptStream(ctx)
			require.NoError(t, err, "failed with message %s", msg)
			buff := make([]byte, 16384)
			n, err := stream.Read(buff)
			// n, err := io.ReadFull(stream, buff)
			require.NoError(t, err, "failed with message %s", msg)
			messages <- string(buff[:n])
			// err = stream.Close()
			// require.NoError(t, err, "failed with message %s", msg)
			// err = listener.Close()
			// require.NoError(t, err, "failed with message %s", msg)
			t.Logf("server end at %s", serverAddr)
		}()
	}
	runClient := func(serverAddr net.Addr, sessions int, msg string) {
		clientWg.Add(1)
		go func() {
			defer clientWg.Done()
			t.Log("deleteme 1")
			conn, err := dialer.Dial(ctx, serverAddr)
			t.Log("deleteme 2")
			if err != nil {
				var appErr *quic.ApplicationError
				require.True(t, errors.As(err, &appErr))
				t.Logf("message: %s, is remote? %v, code: %v", appErr.ErrorMessage, appErr.Remote, appErr.ErrorCode)
				require.FailNow(t, "deleteme")
			}

			t.Log("deleteme 3")
			require.NoError(t, err, "failed with message %s", msg)
			require.Len(t, dialer.sessions, sessions, "failed with message %s", msg)
			n, err := conn.Write(([]byte)(msg))
			t.Log("deleteme 4")
			require.NoError(t, err, "failed with message %s", msg)
			require.Greater(t, n, 0, "failed with message %s", msg)
			t.Log("deleteme 5")
			select {
			case <-ctx.Done():
				require.FailNow(t, "timeout", "for msg %s", msg)
			case <-messages:
			}
			t.Log("deleteme 6")
			err = conn.Close()
			t.Log("deleteme 7")
			require.NoError(t, err, "failed with message %s", msg)
		}()
	}

	// to 110 with scion
	dst := mockScionAddressWithPath(t, "1-ff00:0:110", "127.0.0.1:12345",
		"1-ff00:0:111", 41, 1, "1-ff00:0:110")
	runServer(dst, "first 110")
	runClient(dst, 1, "hello 110")
	clientWg.Wait()
	serverWg.Wait()

	// deleteme uncomment block below
	// // to 112 with scion
	// dst = mockScionAddressWithPath(t, "1-ff00:0:112", "127.0.0.1:12345",
	// 	"1-ff00:0:111", 41, 1, "1-ff00:0:110", 2, 1, "1-ff00:0:112")
	// runServer(dst, "first 112")
	// runClient(dst, 2, "hello 112")
	// clientWg.Wait()
	// serverWg.Wait()

	// to 110 again with several connections
	time.Sleep(2 * time.Second)
	thisNet.EnableDebugMessages(true)
	// for k := range dialer.sessions {
	// 	delete(dialer.sessions, k)
	// }
	dst = mockScionAddressWithPath(t, "1-ff00:0:110", "127.0.0.1:12345",
		"1-ff00:0:111", 41, 1, "1-ff00:0:110")
	runServer(dst, "second 110")
	runClient(dst, 1, "hello 110")
	clientWg.Wait()
	serverWg.Wait()

	// for p := 0; p < 1; p++ {
	// 	dst = mockScionAddressWithPath(t, "1-ff00:0:110", fmt.Sprintf("127.0.0.1:%d", p+12345),
	// 		"1-ff00:0:111", 41, 1, "1-ff00:0:110")
	// 	runServer(dst)
	// 	runClient(dst, 3+p, "hello 110")
	// }
	// clientWg.Wait()
	// // wait for all servers to finish without errors
	// serverWg.Wait()
}

func TestCloseSession(t *testing.T) {

}
