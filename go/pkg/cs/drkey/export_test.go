// Copyright 2021 ETH Zurich
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

package drkey

import (
	"time"

	"github.com/scionproto/scion/go/lib/addr"
	"github.com/scionproto/scion/go/lib/drkey"
)

func NewTestServiceEngine(localIA addr.IA, svdb drkey.SecretValueDB, masterKey []byte,
	keyDur time.Duration,
	db drkey.Lvl1DB, fetcher Fetcher, list Lvl1PrefetchListKeeper) *serviceEngine {
	return &serviceEngine{
		secretBackend:  newSecretValueBackend(svdb, masterKey, keyDur),
		LocalIA:        localIA,
		DB:             db,
		Fetcher:        fetcher,
		prefetchKeeper: list,
	}
}

func FromPrefetcher() fromPrefetcher {
	return fromPrefetcher{}
}
