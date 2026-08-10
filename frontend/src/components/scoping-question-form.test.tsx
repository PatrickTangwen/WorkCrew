import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

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

function answerEveryQuestion() {
  fireEvent.change(screen.getByRole("textbox", { name: "What is one row?" }), {
    target: { value: "One source folder." },
  })
  fireEvent.click(screen.getByRole("radio", { name: "Fall" }))
  fireEvent.click(screen.getByRole("checkbox", { name: "Alpha" }))
  fireEvent.click(screen.getByRole("checkbox", { name: "Beta" }))
  fireEvent.click(screen.getByRole("radio", { name: "Yes" }))
}

function renderForm(props: Partial<Parameters<typeof ScopingQuestionForm>[0]> = {}) {
  const onSubmit = vi.fn()
  const view = render(
    <ScopingQuestionForm
      questions={questions}
      status="ready"
      error={null}
      onSubmit={onSubmit}
      {...props}
    />
  )
  return { onSubmit, view }
}

describe("ScopingQuestionForm", () => {
  afterEach(cleanup)

  it("renders each question type and submits one typed answers payload", () => {
    const { onSubmit } = renderForm()

    answerEveryQuestion()
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))

    expect(onSubmit).toHaveBeenCalledWith({
      Q1: { value: "One source folder.", note: null },
      Q2: { value: "fall", note: null },
      Q3: { value: ["alpha", "beta"], note: null },
      Q4: { value: true, note: null },
    })
  })

  it("sends a note typed beside a chosen option", () => {
    const { onSubmit } = renderForm()

    answerEveryQuestion()
    fireEvent.change(
      screen.getByRole("textbox", { name: "Note for Which period applies?" }),
      { target: { value: "  Except beta, which spans both.  " } }
    )
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))

    expect(vi.mocked(onSubmit).mock.calls[0][0].Q2).toEqual({
      value: "fall",
      note: "Except beta, which spans both.",
    })
  })

  it("offers no note box on a question that is already free text", () => {
    renderForm()

    expect(
      screen.queryByRole("textbox", { name: "Note for What is one row?" })
    ).toBeNull()
  })

  it("clears the previous round's answers when new questions arrive", () => {
    const { onSubmit, view } = renderForm()
    answerEveryQuestion()

    const nextRound: ScopingQuestion[] = [
      { id: "Q1", question: "Which mapping applies?", type: "text", options: null },
    ]
    view.rerender(
      <ScopingQuestionForm
        questions={nextRound}
        status="ready"
        error={null}
        onSubmit={onSubmit}
      />
    )

    // The stale answer must not be submitted as this round's.
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(
      screen.getByText("Answer every question before resuming the run.")
    ).toBeVisible()

    fireEvent.change(
      screen.getByRole("textbox", { name: "Which mapping applies?" }),
      { target: { value: "Use the broader region." } }
    )
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))
    expect(onSubmit).toHaveBeenCalledWith({
      Q1: { value: "Use the broader region.", note: null },
    })
  })
})
