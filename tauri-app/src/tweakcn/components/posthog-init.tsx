"use client";

import { useEffect } from "react";
import { initPostHog } from "@/tweakcn/lib/posthog";

export function PostHogInit() {
  useEffect(() => {
    initPostHog();
  }, []);

  return null;
}
