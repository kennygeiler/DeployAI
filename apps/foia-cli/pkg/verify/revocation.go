package verify

import (
	"encoding/json"
	"fmt"
	"os"
)

type edgeRevocationEntry struct {
	DeviceID        string `json:"deviceId"`
	RevokedAtUnixMs int64  `json:"revokedAtUnixMs"`
}

type edgeRevocationFile struct {
	Revocations []edgeRevocationEntry `json:"revocations"`
}

func loadEdgeRevocationFile(path string) (*edgeRevocationFile, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var f edgeRevocationFile
	if err := json.Unmarshal(b, &f); err != nil {
		return nil, err
	}
	return &f, nil
}

func checkEdgeRevocation(deviceID string, createdAtUnixMs int64, f *edgeRevocationFile) error {
	for _, e := range f.Revocations {
		if e.DeviceID != deviceID {
			continue
		}
		if createdAtUnixMs >= e.RevokedAtUnixMs {
			return fmt.Errorf(
				"bundle created at or after edge revocation (deviceId=%s createdAtUnixMs=%d revokedAtUnixMs=%d)",
				deviceID, createdAtUnixMs, e.RevokedAtUnixMs,
			)
		}
	}
	return nil
}
