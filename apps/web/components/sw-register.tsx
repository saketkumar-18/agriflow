"use client";

import { useEffect } from "react";

export function SwRegister() {
  useEffect(() => {
    if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* SW optional — app works without it */
      });
    }
  }, []);
  return null;
}
