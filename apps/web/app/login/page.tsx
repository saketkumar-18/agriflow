"use client";

import { Suspense } from "react";
import { LoginPage } from "./client";

export default function LoginRoute() {
  return (
    <Suspense fallback={null}>
      <LoginPage />
    </Suspense>
  );
}
