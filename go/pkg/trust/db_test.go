// Copyright 2020 Anapaya Systems
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

package trust_test

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/scionproto/scion/go/lib/addr"
	"github.com/scionproto/scion/go/lib/xtest"
	"github.com/scionproto/scion/go/pkg/command"
	"github.com/scionproto/scion/go/pkg/trust"
	"github.com/scionproto/scion/go/scion-pki/testcrypto"
	"github.com/scionproto/scion/go/scion-pki/trcs"
)

var updateNonDeterministic = xtest.UpdateNonDeterminsticGoldenFiles()

var goldenDir = "./testdata/common"

func TestUpdateCerts(t *testing.T) {
	if !(*updateNonDeterministic) {
		t.Skip("Specify -update-non-deterministic to update certs")
		return
	}
	dir, cleanF := xtest.MustTempDir("", "tmp")
	defer cleanF()

	cmd := testcrypto.Cmd(command.StringPather(""))
	cmd.SetArgs([]string{
		"-t", "testdata/golden.topo",
		"-o", dir,
		"--isd-dir",
		"--as-validity", "1y",
	})
	err := cmd.Execute()
	require.NoError(t, err)

	cmd.SetArgs([]string{"update", "-o", dir})
	err = cmd.Execute()
	require.NoError(t, err)

	cmd = trcs.Cmd(command.StringPather(""))
	cmd.SetArgs([]string{
		"format",
		"--out=" + filepath.Join(dir, "ISD1/trcs/ISD1-B1-S1.pem.trc"),
		filepath.Join(dir, "ISD1/trcs/ISD1-B1-S1.trc"),
	})
	err = cmd.Execute()
	require.NoError(t, err)

	err = os.WriteFile(filepath.Join(dir, "certs", "dummy.pem"), []byte{}, 0666)
	require.NoError(t, err)

	out, err := exec.Command("rm", "-rf", goldenDir).CombinedOutput()
	require.NoError(t, err, string(out))

	out, err = exec.Command("mv", dir, goldenDir).CombinedOutput()
	require.NoError(t, err, string(out))
}

type chainQueryMatcher struct {
	ia   addr.IA
	skid []byte
}

func (m chainQueryMatcher) Matches(x interface{}) bool {
	v, ok := x.(trust.ChainQuery)
	if !ok {
		return false
	}
	return v.IA.Equal(m.ia) && bytes.Equal(v.SubjectKeyID, m.skid)
}

func (m chainQueryMatcher) String() string {
	return fmt.Sprintf("%+v, %+v", m.ia, m.skid)
}

type ctxMatcher struct{}

func (m ctxMatcher) Matches(x interface{}) bool {
	_, ok := x.(context.Context)
	return ok
}

func (m ctxMatcher) String() string {
	return "it should be context.context"
}

func loadKey(t *testing.T, file string) *ecdsa.PrivateKey {
	t.Helper()
	raw, err := os.ReadFile(file)
	require.NoError(t, err)
	block, _ := pem.Decode(raw)
	if block == nil || block.Type != "PRIVATE KEY" {
		panic("no valid private key block")
	}
	key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	require.NoError(t, err)
	ret, ok := key.(*ecdsa.PrivateKey)
	if !ok {
		panic("no valid ecdsa key")
	}
	return ret
}
