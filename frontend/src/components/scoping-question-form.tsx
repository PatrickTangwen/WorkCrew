import { useEffect, useState, type ComponentType, type FormEvent } from "react"

import type {
  ScopingAnswers,
  ScopingAnswerValue,
  ScopingQuestion,
  ScopingQuestionType,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type FormStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type ScopingQuestionFormProps = {
  questions: ScopingQuestion[]
  status: FormStatus
  error: string | null
  onSubmit: (answers: ScopingAnswers) => void
}

type QuestionControlProps = {
  question: ScopingQuestion
  answer: ScopingAnswerValue | undefined
  onChange: (answer: ScopingAnswerValue) => void
}

type Choice = {
  key: string
  value: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

const textareaClass =
  "w-full resize-y rounded-[9px] border border-line bg-surface px-3 py-2.5 text-[12.5px] leading-[1.5] text-ink outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"

function ChoiceList({
  questionId,
  inputType,
  choices,
}: {
  questionId: string
  inputType: "radio" | "checkbox"
  choices: Choice[]
}) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {choices.map((choice) => (
        <label
          key={choice.key}
          className={cn(
            "flex cursor-pointer items-center gap-2.5 rounded-[9px] border bg-surface px-3 py-2.5 text-[12.5px] text-ink",
            choice.checked ? "border-brand" : "border-line"
          )}
        >
          <input
            type={inputType}
            name={questionId}
            value={choice.value}
            checked={choice.checked}
            onChange={(event) => choice.onChange(event.target.checked)}
            className="sr-only"
          />
          <span
            aria-hidden="true"
            className={cn(
              "grid size-[15px] shrink-0 place-items-center border-[1.5px]",
              inputType === "checkbox" ? "rounded-[4px]" : "rounded-full",
              choice.checked ? "border-brand bg-brand" : "border-line-dash bg-white"
            )}
          >
            <span
              className={cn(
                "size-1.5 bg-white",
                inputType === "checkbox" ? "rounded-[1px]" : "rounded-full",
                !choice.checked && "opacity-0"
              )}
            />
          </span>
          {choice.label}
        </label>
      ))}
    </div>
  )
}

function answered(answer: ScopingAnswerValue | undefined) {
  if (Array.isArray(answer)) return answer.length > 0
  if (typeof answer === "string") return answer.trim().length > 0
  return typeof answer === "boolean"
}

function TextQuestion({ question, answer, onChange }: QuestionControlProps) {
  return (
    <textarea
      aria-label={question.question}
      value={typeof answer === "string" ? answer : ""}
      onChange={(event) => onChange(event.target.value)}
      rows={3}
      placeholder="Type your answer"
      className={cn(textareaClass, "mt-3")}
    />
  )
}

function SingleSelectQuestion({
  question,
  answer,
  onChange,
}: QuestionControlProps) {
  return (
    <ChoiceList
      questionId={question.id}
      inputType="radio"
      choices={(question.options ?? []).map((option) => ({
        key: option.value,
        value: option.value,
        label: option.label,
        checked: answer === option.value,
        onChange: () => onChange(option.value),
      }))}
    />
  )
}

function MultiSelectQuestion({
  question,
  answer,
  onChange,
}: QuestionControlProps) {
  const selected = Array.isArray(answer) ? answer : []
  return (
    <ChoiceList
      questionId={question.id}
      inputType="checkbox"
      choices={(question.options ?? []).map((option) => ({
        key: option.value,
        value: option.value,
        label: option.label,
        checked: selected.includes(option.value),
        onChange: (checked) =>
          onChange(
            checked
              ? [...selected, option.value]
              : selected.filter((candidate) => candidate !== option.value)
          ),
      }))}
    />
  )
}

function ConfirmQuestion({ question, answer, onChange }: QuestionControlProps) {
  const choices = [
    { label: "Yes", value: true },
    { label: "No", value: false },
  ]
  return (
    <ChoiceList
      questionId={question.id}
      inputType="radio"
      choices={choices.map((choice) => ({
        key: String(choice.value),
        value: String(choice.value),
        label: choice.label,
        checked: answer === choice.value,
        onChange: () => onChange(choice.value),
      }))}
    />
  )
}

const questionControls: Record<
  ScopingQuestionType,
  ComponentType<QuestionControlProps>
> = {
  text: TextQuestion,
  single_select: SingleSelectQuestion,
  multi_select: MultiSelectQuestion,
  confirm: ConfirmQuestion,
}

function ScopingQuestionForm({
  questions,
  status,
  error,
  onSubmit,
}: ScopingQuestionFormProps) {
  const [values, setValues] = useState<Record<string, ScopingAnswerValue>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [validationError, setValidationError] = useState<string | null>(null)

  // A later round reuses this component, so its answers must not carry
  // over from the round before.
  useEffect(() => {
    setValues({})
    setNotes({})
    setValidationError(null)
  }, [questions])

  function setValue(id: string, value: ScopingAnswerValue) {
    setValues((current) => ({ ...current, [id]: value }))
    setValidationError(null)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!questions.every((question) => answered(values[question.id]))) {
      setValidationError("Answer every question before resuming the run.")
      return
    }
    const answers: ScopingAnswers = Object.fromEntries(
      questions.map((question) => [
        question.id,
        {
          value: values[question.id],
          note: notes[question.id]?.trim() || null,
        },
      ])
    )
    onSubmit(answers)
  }

  const done = questions.filter((question) => answered(values[question.id])).length

  return (
    <section className="overflow-hidden rounded-[14px] border border-brand/26 bg-surface shadow-[0_1px_3px_rgba(31,30,28,.05)]">
      <div className="border-b border-line-soft bg-brand/8 px-5 py-4">
        <h2 className="text-sm font-medium text-ink">Scoping questions</h2>
        <p className="mt-1 text-xs text-subtle">
          The workflow needs a few decisions before extraction can continue.
        </p>
      </div>

      {status === "loading" || status === "idle" ? (
        <p className="py-8 text-center text-sm text-faint">Loading questions…</p>
      ) : (
        <form className="flex flex-col gap-3 p-4" onSubmit={submit}>
          {questions.map((question, index) => {
            const type = question.type ?? "text"
            const QuestionControl = questionControls[type]
            return (
              <fieldset
                key={question.id}
                className="rounded-[11px] border border-line bg-paper p-[15px]"
              >
                <legend className="flex gap-2.5 px-1 text-[13px] leading-[1.45] font-medium text-ink">
                  <span className="pt-0.5 font-mono text-[11px] text-ghost">
                    {index + 1}
                  </span>
                  {question.question}
                </legend>

                <QuestionControl
                  question={question}
                  answer={values[question.id]}
                  onChange={(value) => setValue(question.id, value)}
                />

                {type !== "text" && (
                  <label className="mt-3 block">
                    <span className="text-[11px] text-faint">
                      Add anything the options do not cover (optional)
                    </span>
                    <textarea
                      aria-label={`Note for ${question.question}`}
                      value={notes[question.id] ?? ""}
                      onChange={(event) =>
                        setNotes((current) => ({
                          ...current,
                          [question.id]: event.target.value,
                        }))
                      }
                      rows={2}
                      className={cn(textareaClass, "mt-1.5")}
                    />
                  </label>
                )}
              </fieldset>
            )
          })}

          {(validationError || error) && (
            <p
              role="alert"
              className="rounded-[9px] border border-bad-line bg-bad-wash px-3 py-2.5 text-xs text-bad"
            >
              {validationError ?? error}
            </p>
          )}

          <div className="flex items-center justify-between gap-3.5 pt-0.5">
            <p className="text-xs text-faint">
              {done} of {questions.length} answered
            </p>
            <button
              type="submit"
              disabled={status === "submitting"}
              className="h-[37px] cursor-pointer rounded-[9px] bg-brand px-[18px] text-[13px] font-medium text-white transition-colors hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-default disabled:opacity-70"
            >
              {status === "submitting" ? "Resuming…" : "Submit answers"}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

export { ScopingQuestionForm }
