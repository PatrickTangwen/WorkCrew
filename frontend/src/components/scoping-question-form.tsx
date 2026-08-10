import { useState, type ComponentType, type FormEvent } from "react"
import { CircleHelp, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type {
  ScopingAnswer,
  ScopingAnswers,
  ScopingQuestion,
  ScopingQuestionType,
} from "@/lib/api"

type FormStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type ScopingQuestionFormProps = {
  questions: ScopingQuestion[]
  status: FormStatus
  error: string | null
  onSubmit: (answers: ScopingAnswers) => void
}

type QuestionControlProps = {
  question: ScopingQuestion
  answer: ScopingAnswer | undefined
  onChange: (answer: ScopingAnswer) => void
}

type Choice = {
  key: string
  value: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

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
          className="flex cursor-pointer items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-sm"
        >
          <input
            type={inputType}
            name={questionId}
            value={choice.value}
            checked={choice.checked}
            onChange={(event) => choice.onChange(event.target.checked)}
          />
          {choice.label}
        </label>
      ))}
    </div>
  )
}

function answered(answer: ScopingAnswer | undefined) {
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
      className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
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
  const [answers, setAnswers] = useState<ScopingAnswers>({})
  const [validationError, setValidationError] = useState<string | null>(null)

  function setAnswer(id: string, answer: ScopingAnswer) {
    setAnswers((current) => ({ ...current, [id]: answer }))
    setValidationError(null)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!questions.every((question) => answered(answers[question.id]))) {
      setValidationError("Answer every question before resuming the run.")
      return
    }
    onSubmit(answers)
  }

  return (
    <Card className="bg-background">
      <CardHeader className="border-b">
        <CardTitle
          role="heading"
          aria-level={2}
          className="flex items-center gap-2"
        >
          <CircleHelp className="size-4" /> Scoping questions
        </CardTitle>
        <CardDescription>
          The workflow needs a few decisions before extraction can continue.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {status === "loading" || status === "idle" ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Loading questions…
          </p>
        ) : (
          <form className="space-y-4" onSubmit={submit}>
            {questions.map((question, index) => {
              const type = question.type ?? "text"
              const answer = answers[question.id]
              const QuestionControl = questionControls[type]
              return (
                <fieldset
                  key={question.id}
                  className="rounded-xl border bg-muted/18 p-4"
                >
                  <legend className="px-1 text-sm font-medium">
                    <span className="mr-2 font-mono text-xs text-muted-foreground">
                      {index + 1}
                    </span>
                    {question.question}
                  </legend>

                  <QuestionControl
                    question={question}
                    answer={answer}
                    onChange={(value) => setAnswer(question.id, value)}
                  />
                </fieldset>
              )
            })}

            {(validationError || error) && (
              <p role="alert" className="text-sm text-destructive">
                {validationError ?? error}
              </p>
            )}
            <div className="flex justify-end">
              <Button type="submit" disabled={status === "submitting"}>
                <Send />
                {status === "submitting" ? "Resuming…" : "Submit answers"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

export { ScopingQuestionForm }
