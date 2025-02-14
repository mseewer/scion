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

package cs

import (
	"context"
	"hash"
	"net"
	"time"

	"github.com/scionproto/scion/go/cs/beacon"
	"github.com/scionproto/scion/go/cs/beaconing"
	"github.com/scionproto/scion/go/cs/ifstate"
	"github.com/scionproto/scion/go/lib/addr"
	"github.com/scionproto/scion/go/lib/ctrl/seg"
	"github.com/scionproto/scion/go/lib/infra/modules/seghandler"
	"github.com/scionproto/scion/go/lib/metrics"
	"github.com/scionproto/scion/go/lib/pathdb"
	"github.com/scionproto/scion/go/lib/periodic"
	"github.com/scionproto/scion/go/lib/revcache"
	"github.com/scionproto/scion/go/lib/snet"
	"github.com/scionproto/scion/go/lib/snet/addrutil"
	"github.com/scionproto/scion/go/pkg/cs/drkey"
	"github.com/scionproto/scion/go/pkg/hiddenpath"
	"github.com/scionproto/scion/go/pkg/trust"
)

// TasksConfig holds the necessary configuration to start the periodic tasks a
// CS is expected to run.
type TasksConfig struct {
	Core       bool
	IA         addr.IA
	MTU        uint16
	NextHopper interface {
		UnderlayNextHop(uint16) *net.UDPAddr
	}
	Public                *net.UDPAddr
	AllInterfaces         *ifstate.Interfaces
	PropagationInterfaces func() []*ifstate.Interface
	OriginationInterfaces func() []*ifstate.Interface
	TrustDB               trust.DB
	PathDB                pathdb.DB
	RevCache              revcache.RevCache
	BeaconSenderFactory   beaconing.SenderFactory
	SegmentRegister       beaconing.RPC
	BeaconStore           Store
	Signer                seg.Signer
	Inspector             trust.Inspector
	Metrics               *Metrics
	DRKeyEngine           drkey.ServiceEngine

	MACGen     func() hash.Hash
	StaticInfo func() *beaconing.StaticInfoCfg

	OriginationInterval  time.Duration
	PropagationInterval  time.Duration
	RegistrationInterval time.Duration
	DRKeyEpochInterval   time.Duration
	// HiddenPathRegistrationCfg contains the required options to configure
	// hidden paths down segment registration. If it is nil, normal path
	// registration is used instead.
	HiddenPathRegistrationCfg *HiddenPathRegistrationCfg

	AllowIsdLoop bool
}

// Originator starts a periodic beacon origination task. For non-core ASes, no
// periodic runner is started.
func (t *TasksConfig) Originator() *periodic.Runner {
	if !t.Core {
		return nil
	}
	s := &beaconing.Originator{
		Extender: t.extender("originator", t.IA, t.MTU, func() uint8 {
			return t.BeaconStore.MaxExpTime(beacon.PropPolicy)
		}),
		SenderFactory:         t.BeaconSenderFactory,
		IA:                    t.IA,
		AllInterfaces:         t.AllInterfaces,
		OriginationInterfaces: t.OriginationInterfaces,
		Signer:                t.Signer,
		Tick:                  beaconing.NewTick(t.OriginationInterval),
	}
	if t.Metrics != nil {
		s.Originated = metrics.NewPromCounter(t.Metrics.BeaconingOriginatedTotal)
	}
	return periodic.Start(s, 500*time.Millisecond, t.OriginationInterval)
}

// Propagator starts a periodic beacon propagation task.
func (t *TasksConfig) Propagator() *periodic.Runner {
	p := &beaconing.Propagator{
		Extender: t.extender("propagator", t.IA, t.MTU, func() uint8 {
			return t.BeaconStore.MaxExpTime(beacon.PropPolicy)
		}),
		SenderFactory:         t.BeaconSenderFactory,
		Provider:              t.BeaconStore,
		IA:                    t.IA,
		Signer:                t.Signer,
		AllInterfaces:         t.AllInterfaces,
		PropagationInterfaces: t.PropagationInterfaces,
		AllowIsdLoop:          t.AllowIsdLoop,
		Tick:                  beaconing.NewTick(t.PropagationInterval),
	}
	if t.Metrics != nil {
		p.Propagated = metrics.NewPromCounter(t.Metrics.BeaconingPropagatedTotal)
		p.InternalErrors = metrics.NewPromCounter(t.Metrics.BeaconingPropagatorInternalErrorsTotal)
	}
	return periodic.Start(p, 500*time.Millisecond, t.PropagationInterval)
}

// SegmentWriters starts periodic segment registration tasks.
func (t *TasksConfig) SegmentWriters() []*periodic.Runner {
	if t.Core {
		return []*periodic.Runner{t.segmentWriter(seg.TypeCore, beacon.CoreRegPolicy)}
	}
	return []*periodic.Runner{
		t.segmentWriter(seg.TypeDown, beacon.DownRegPolicy),
		t.segmentWriter(seg.TypeUp, beacon.UpRegPolicy),
	}
}

func (t *TasksConfig) segmentWriter(segType seg.Type,
	policyType beacon.PolicyType) *periodic.Runner {

	var internalErr, registered metrics.Counter
	if t.Metrics != nil {
		internalErr = metrics.NewPromCounter(t.Metrics.BeaconingRegistrarInternalErrorsTotal)
		registered = metrics.NewPromCounter(t.Metrics.BeaconingRegisteredTotal)
	}
	var writer beaconing.Writer
	switch {
	case segType != seg.TypeDown:
		writer = &beaconing.LocalWriter{
			InternalErrors: metrics.CounterWith(internalErr, "seg_type", segType.String()),
			Registered:     registered,
			Type:           segType,
			Intfs:          t.AllInterfaces,
			Extender: t.extender("registrar", t.IA, t.MTU, func() uint8 {
				return t.BeaconStore.MaxExpTime(policyType)
			}),
			Store: &seghandler.DefaultStorage{PathDB: t.PathDB},
		}

	case t.HiddenPathRegistrationCfg != nil:
		writer = &hiddenpath.BeaconWriter{
			InternalErrors: metrics.CounterWith(internalErr, "seg_type", segType.String()),
			Registered:     registered,
			Intfs:          t.AllInterfaces,
			Extender: t.extender("registrar", t.IA, t.MTU, func() uint8 {
				return t.BeaconStore.MaxExpTime(policyType)
			}),
			RPC: t.HiddenPathRegistrationCfg.RPC,
			Pather: addrutil.Pather{
				NextHopper: t.NextHopper,
			},
			RegistrationPolicy: t.HiddenPathRegistrationCfg.Policy,
			AddressResolver: hiddenpath.RegistrationResolver{
				Router:     t.HiddenPathRegistrationCfg.Router,
				Discoverer: t.HiddenPathRegistrationCfg.Discoverer,
			},
		}
	default:
		writer = &beaconing.RemoteWriter{
			InternalErrors: metrics.CounterWith(internalErr, "seg_type", segType.String()),
			Registered:     registered,
			Type:           segType,
			Intfs:          t.AllInterfaces,
			Extender: t.extender("registrar", t.IA, t.MTU, func() uint8 {
				return t.BeaconStore.MaxExpTime(policyType)
			}),
			RPC: t.SegmentRegister,
			Pather: addrutil.Pather{
				NextHopper: t.NextHopper,
			},
		}
	}
	r := &beaconing.WriteScheduler{
		Provider: t.BeaconStore,
		Intfs:    t.AllInterfaces,
		Type:     segType,
		Writer:   writer,
		Tick:     beaconing.NewTick(t.RegistrationInterval),
	}
	return periodic.Start(r, 500*time.Millisecond, t.RegistrationInterval)
}

func (t *TasksConfig) extender(task string, ia addr.IA, mtu uint16,
	maxExp func() uint8) beaconing.Extender {

	return &beaconing.DefaultExtender{
		IA:         ia,
		Signer:     t.Signer,
		MAC:        t.MACGen,
		Intfs:      t.AllInterfaces,
		MTU:        mtu,
		MaxExpTime: func() uint8 { return maxExp() },
		StaticInfo: t.StaticInfo,
		Task:       task,
		EPIC:       false,
	}
}

func (t *TasksConfig) DRKeyLvl1Cleaner() *periodic.Runner {
	if t.DRKeyEngine == nil {
		return nil
	}
	cleanerPeriod := 2 * t.DRKeyEpochInterval
	return periodic.Start(drkey.NewServiceEngineCleaner(t.DRKeyEngine),
		cleanerPeriod, cleanerPeriod)
}

func (t *TasksConfig) DRKeyPrefetcher() *periodic.Runner {
	if t.DRKeyEngine == nil {
		return nil
	}
	prefetchPeriod := t.DRKeyEpochInterval / 2
	return periodic.Start(
		&drkey.Prefetcher{
			LocalIA:     t.IA,
			Engine:      t.DRKeyEngine,
			KeyDuration: t.DRKeyEpochInterval,
		},
		prefetchPeriod, prefetchPeriod)
}

// Tasks keeps track of the running tasks.
type Tasks struct {
	Originator      *periodic.Runner
	Propagator      *periodic.Runner
	Registrars      []*periodic.Runner
	DRKeyPrefetcher *periodic.Runner

	BeaconCleaner    *periodic.Runner
	PathCleaner      *periodic.Runner
	DRKeyLvl1Cleaner *periodic.Runner
	DRKeySVCleaner   *periodic.Runner
}

func StartTasks(cfg TasksConfig) (*Tasks, error) {

	segCleaner := pathdb.NewCleaner(cfg.PathDB, "control_pathstorage_segments")
	segRevCleaner := revcache.NewCleaner(cfg.RevCache, "control_pathstorage_revocation")
	return &Tasks{
		Originator:      cfg.Originator(),
		Propagator:      cfg.Propagator(),
		Registrars:      cfg.SegmentWriters(),
		DRKeyPrefetcher: cfg.DRKeyPrefetcher(),
		PathCleaner: periodic.Start(
			periodic.Func{
				Task: func(ctx context.Context) {
					segCleaner.Run(ctx)
					segRevCleaner.Run(ctx)
				},
				TaskName: "control_pathstorage_cleaner",
			},
			10*time.Second,
			10*time.Second,
		),
		DRKeyLvl1Cleaner: cfg.DRKeyLvl1Cleaner(),
	}, nil

}

// Kill stops all running tasks immediately.
func (t *Tasks) Kill() {
	if t == nil {
		return
	}
	killRunners([]*periodic.Runner{
		t.Originator,
		t.Propagator,
		t.DRKeyPrefetcher,
		t.PathCleaner,
		t.DRKeyLvl1Cleaner,
		t.DRKeySVCleaner,
	})
	killRunners(t.Registrars)
	t.Originator = nil
	t.Propagator = nil
	t.DRKeyPrefetcher = nil
	t.PathCleaner = nil
	t.DRKeyLvl1Cleaner = nil
	t.DRKeySVCleaner = nil
	t.Registrars = nil
}

func killRunners(runners []*periodic.Runner) {
	for _, r := range runners {
		r.Kill()
	}
}

// HiddenPathRegistrationCfg contains the required options to configure hidden
// paths down segment registration.
type HiddenPathRegistrationCfg struct {
	Policy     hiddenpath.RegistrationPolicy
	Router     snet.Router
	Discoverer hiddenpath.Discoverer
	RPC        hiddenpath.Register
}

// Store is the interface to interact with the beacon store.
type Store interface {
	// PreFilter indicates whether the beacon will be filtered on insert by
	// returning an error with the reason. This allows the caller to drop
	// ignored beacons.
	PreFilter(beacon beacon.Beacon) error
	// BeaconsToPropagate returns an error and an empty slice if an error (e.g., connection or
	// parsing error) occurs; otherwise, it returns a slice containing the beacons (which
	// potentially could be empty when no beacon is found) and no error.
	// The selection is based on the configured propagation policy.
	BeaconsToPropagate(ctx context.Context) ([]beacon.Beacon, error)
	// SegmentsToRegister returns an error and an empty slice if an error (e.g., connection or
	// parsing error) occurs; otherwise, it returns a slice containing the beacons (which
	// potentially could be empty when no beacon is found) and no error.
	// The selections is based on the configured propagation policy for the requested segment type.
	SegmentsToRegister(ctx context.Context, segType seg.Type) ([]beacon.Beacon, error)
	// InsertBeacon adds a verified beacon to the store, ignoring revocations.
	InsertBeacon(ctx context.Context, beacon beacon.Beacon) (beacon.InsertStats, error)
	// UpdatePolicy updates the policy. Beacons that are filtered by all
	// policies after the update are removed.
	UpdatePolicy(ctx context.Context, policy beacon.Policy) error
	// MaxExpTime returns the segment maximum expiration time for the given policy.
	MaxExpTime(policyType beacon.PolicyType) uint8
}
