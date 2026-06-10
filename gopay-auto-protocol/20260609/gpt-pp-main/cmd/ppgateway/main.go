package main

import (
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"pp-longlink/internal/gateway"
)

func main() {
	addr := flag.String("addr", ":8787", "listen address")
	staticDir := flag.String("static", "webapp/static", "static directory")
	timeout := flag.Duration("timeout", 30*time.Second, "per upstream HTTP operation timeout")
	maxAttempts := flag.Int("attempts", 4, "retry attempts per proxy candidate")
	checkoutParallel := flag.Int("checkout-parallel", 1, "checkout creation parallelism; keep 1 for one token")
	raceParallel := flag.Int("race-parallel", 3, "parallelism for custom PayPal confirm across derived proxies")
	proxyRotations := flag.Int("proxy-rotations", 6, "derived proxy rotations per proxy")
	allowNonZero := flag.Bool("allow-non-zero", true, "allow non-zero checkout amounts when extracting authorize URL")
	usePythonFallback := flag.Bool("python-fallback", false, "enable bundled Python fallback after Go extraction miss")
	logFile := flag.String("log-file", "", "write gateway logs to this file as well as stdout")
	flag.Parse()

	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	if *logFile != "" {
		f, err := os.OpenFile(*logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
		if err != nil {
			log.Fatalf("open log file %s failed: %v", *logFile, err)
		}
		defer f.Close()
		log.SetOutput(io.MultiWriter(os.Stdout, f))
	}

	cfg := gateway.DefaultConfig()
	cfg.Timeout = *timeout
	cfg.MaxAttempts = *maxAttempts
	cfg.CheckoutParallel = *checkoutParallel
	cfg.RaceParallel = *raceParallel
	cfg.ProxyRotations = *proxyRotations
	cfg.Country = "US"
	cfg.Currency = "USD"
	cfg.AllowNonZero = *allowNonZero
	cfg.UsePythonFallback = *usePythonFallback
	extractor := gateway.NewExtractor(cfg)
	srv := gateway.NewServer(extractor)
	mux := http.NewServeMux()
	srv.Register(mux)
	if st, err := os.Stat(*staticDir); err == nil && st.IsDir() {
		static := http.FileServer(http.Dir(*staticDir))
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
			w.Header().Set("Pragma", "no-cache")
			static.ServeHTTP(w, r)
		})
	}
	log.Printf(
		"pp gateway go runtime listening on %s timeout=%s attempts=%d checkout_parallel=%d race_parallel=%d proxy_rotations=%d allow_non_zero=%t python_fallback=%t",
		*addr,
		cfg.Timeout,
		cfg.MaxAttempts,
		cfg.CheckoutParallel,
		cfg.RaceParallel,
		cfg.ProxyRotations,
		cfg.AllowNonZero,
		cfg.UsePythonFallback,
	)
	log.Fatal(http.ListenAndServe(*addr, mux))
}
