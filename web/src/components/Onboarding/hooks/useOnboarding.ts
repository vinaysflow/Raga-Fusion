import { useEffect, useState } from "react";

export interface OnboardingState {
  currentStep: number;
  completedSteps: number[];
  userProgress: {
    hasGeneratedTrack: boolean;
    hasPlayedTrack: boolean;
    hasDownloaded: boolean;
  };
}

const KEY = "onboarding_state_v1";
const COMPLETE_KEY = "onboarding_completed";

const defaultState: OnboardingState = {
  currentStep: 0,
  completedSteps: [],
  userProgress: {
    hasGeneratedTrack: false,
    hasPlayedTrack: false,
    hasDownloaded: false,
  },
};

export function useOnboarding() {
  const [state, setState] = useState<OnboardingState>(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      // no-op
    }
    return defaultState;
  });

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(state));
  }, [state]);

  const completed = localStorage.getItem(COMPLETE_KEY) === "true";

  return {
    state,
    completed,
    goToStep: (step: number) => setState((s) => ({ ...s, currentStep: step })),
    markCompletedStep: (step: number) =>
      setState((s) => ({
        ...s,
        completedSteps: Array.from(new Set([...s.completedSteps, step])),
      })),
    setProgress: (progress: Partial<OnboardingState["userProgress"]>) =>
      setState((s) => ({ ...s, userProgress: { ...s.userProgress, ...progress } })),
    skipAll: () => {
      localStorage.setItem(COMPLETE_KEY, "true");
      setState((s) => ({ ...s, currentStep: 4 }));
    },
    completeAll: () => {
      localStorage.setItem(COMPLETE_KEY, "true");
      setState((s) => ({ ...s, currentStep: 4, completedSteps: [0, 1, 2, 3, 4] }));
    },
  };
}
