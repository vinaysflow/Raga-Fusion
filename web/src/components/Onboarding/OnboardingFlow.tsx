import WelcomeScreen from "./steps/WelcomeScreen";
import ExplainMagic from "./steps/ExplainMagic";
import InteractiveDemo from "./steps/InteractiveDemo";
import FirstSuccess from "./steps/FirstSuccess";
import AccountPrompt from "./steps/AccountPrompt";
import { useOnboarding } from "./hooks/useOnboarding";

interface Props {
  onFinish: () => void;
}

export default function OnboardingFlow({ onFinish }: Props) {
  const { state, goToStep, markCompletedStep, skipAll, completeAll } = useOnboarding();

  const next = () => {
    markCompletedStep(state.currentStep);
    goToStep(Math.min(state.currentStep + 1, 4));
  };

  const done = () => {
    completeAll();
    onFinish();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 rounded-2xl border border-white/10 bg-neutral-950/95 p-5">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {Array.from({ length: 5 }, (_, i) => (
            <button
              key={i}
              type="button"
              className={`h-2 w-8 rounded-full ${i <= state.currentStep ? "bg-indigo-500" : "bg-white/20"}`}
              onClick={() => {
                if (state.completedSteps.includes(i) || i <= state.currentStep) goToStep(i);
              }}
              aria-label={`Go to onboarding step ${i + 1}`}
            />
          ))}
        </div>
        <button type="button" className="text-xs text-neutral-400 hover:text-neutral-200" onClick={skipAll}>
          Skip onboarding
        </button>
      </div>

      {state.currentStep === 0 && <WelcomeScreen onNext={next} />}
      {state.currentStep === 1 && <ExplainMagic onNext={next} />}
      {state.currentStep === 2 && <InteractiveDemo onNext={next} />}
      {state.currentStep === 3 && <FirstSuccess onNext={next} />}
      {state.currentStep >= 4 && <AccountPrompt onDone={done} />}
    </div>
  );
}
