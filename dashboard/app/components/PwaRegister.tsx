"use client";

import { useEffect } from "react";

export default function PwaRegister() {
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      window.addEventListener("load", () => {
        navigator.serviceWorker
          .register("/service-worker.js")
          .catch((error) => {
            console.warn("Service worker registration failed:", error);
          });
      });
    }
  }, []);

  return null;
}
