# Build with: docker build -f apps/foia-cli/Dockerfile -t deployai/foia-cli:dev .
# (from repository root)

FROM golang:1.26-alpine AS build
WORKDIR /src
COPY apps/foia-cli/go.mod ./
RUN go mod download || true
COPY apps/foia-cli/ ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/foia ./cmd/foia

FROM gcr.io/distroless/static:nonroot
COPY --from=build /out/foia /foia
ENTRYPOINT ["/foia"]
