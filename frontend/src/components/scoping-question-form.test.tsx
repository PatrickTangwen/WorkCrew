import { fireEvent, render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { ScopingQuestionForm } from "@/components/scoping-question-form"
import type { ScopingQuestion } from "@/lib/api"

const questions: ScopingQuestion[] = [
  { id: "Q1", question: "What is one row?", type: "text", options: null },
  {
    id: "Q2",
    question: "Which period applies?",
    type: "single_select",
    options: [
      { value: "spring", label: "Spring" },
      { value: "fall", label: "Fall" },
    ],
  },
  {
    id: "Q3",
    question: "Which folders are authoritative?",
    type: "multi_select",
    options: [
      { value: "alpha", label: "Alpha" },
      { value: "beta", label: "Beta" },
    ],
  },
  { id: "Q4", question: "Is this set complete?", type: "confirm", options: null },
]

it("renders each question type and submits one typed answers payload", () => {
  const onSubmit = vi.fn()
  render(
    <ScopingQuestionForm
      questions={questions}
      status="ready"
      error={null}
      onSubmit={onSubmit}
    />
  )

  fireEvent.change(screen.getByRole("textbox", { name: "What is one row?" }), {
    target: { value: "One source folder." },
  })
  fireEvent.click(screen.getByRole("radio", { name: "Fall" }))
  fireEvent.click(screen.getByRole("checkbox", { name: "Alpha" }))
  fireEvent.click(screen.getByRole("checkbox", { name: "Beta" }))
  fireEvent.click(screen.getByRole("radio", { name: "Yes" }))
  fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))

  expect(onSubmit).toHaveBeenCalledWith({
    Q1: "One source folder.",
    Q2: "fall",
    Q3: ["alpha", "beta"],
    Q4: true,
  })
})
