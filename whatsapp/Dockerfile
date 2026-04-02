FROM golang:1.25 AS builder

WORKDIR /src

COPY go.mod .
COPY main.go .

RUN go mod tidy
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -o /out/whatsapp-service ./main.go

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates sqlite3 libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /out/whatsapp-service /app/whatsapp-service

RUN mkdir -p /data

EXPOSE 8081

CMD ["/app/whatsapp-service"]
