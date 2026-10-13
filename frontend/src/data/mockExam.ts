import type { ExamPreview, ExamQuestion } from '../types/exam';

type SampleQuestion = Omit<Extract<ExamQuestion, { type: 'MCQ' }>, 'id'>
  | Omit<Extract<ExamQuestion, { type: 'SHORT_ANSWER' }>, 'id'>;

function mcq(prompt: string, options: readonly string[], language = 'en', direction: 'ltr' | 'rtl' = 'ltr'): SampleQuestion {
  return {
    type: 'MCQ', prompt, marks: 1, language, direction,
    options: options.map((text, index) => ({ id: `option-${index + 1}`, text })),
  };
}

/** Repeat a small sample set to demonstrate the 30-cell palette, not an actual paper. */
function questions(subjectId: string, samples: readonly SampleQuestion[]): ExamQuestion[] {
  return Array.from({ length: 30 }, (_, index) => {
    const sample = samples[index % samples.length];
    return { ...sample, id: `${subjectId}-question-${index + 1}` };
  });
}

/** Synthetic preview content. No answer keys, grading rules, or admission paper. */
export const mockExam: ExamPreview = {
  id: 'sample-exam',
  title: 'CCK entry-test interface preview',
  subjects: [
    {
      id: 'sample-english', name: 'English', durationMinutes: 60,
      questions: questions('english', [
        mcq('Choose the correctly spelled word.', ['beautifull', 'beautiful', 'beutiful', 'beautifal']),
        mcq('Which of the following words is the opposite in meaning to “creation”?', ['creation', 'development', 'destruction', 'progress']),
        { type: 'SHORT_ANSWER', prompt: 'Write the plural of “child”.', marks: 1, language: 'en', maxLength: 100 },
        mcq('Choose the word that best completes the sentence: She ___ to school every day.', ['go', 'goes', 'going', 'gone']),
        mcq('Which word is closest in meaning to “rapid”?', ['slow', 'quick', 'quiet', 'late']),
        { type: 'SHORT_ANSWER', prompt: 'Write the past tense of “walk”.', marks: 1, language: 'en', maxLength: 100 },
      ]),
    },
    {
      id: 'sample-mathematics', name: 'Mathematics', durationMinutes: 60,
      questions: questions('mathematics', [
        mcq('What is 15 × 4?', ['45', '50', '60', '75']),
        { type: 'SHORT_ANSWER', prompt: 'Calculate the product.', expression: '8 × 3', marks: 1, inputMode: 'decimal', maxLength: 100 },
        mcq('What is one quarter of 100?', ['10', '20', '25', '50']),
        { type: 'SHORT_ANSWER', prompt: 'Find the value of x.', expression: '3(x + 5) = 24', marks: 1, inputMode: 'decimal', maxLength: 100 },
        mcq('What is the perimeter of a square with side length 6 cm?', ['12 cm', '18 cm', '24 cm', '36 cm']),
        { type: 'SHORT_ANSWER', prompt: 'Calculate the sum.', expression: '18 + 27', marks: 1, inputMode: 'decimal', maxLength: 100 },
      ]),
    },
    {
      id: 'sample-urdu', name: 'Urdu', durationMinutes: 60,
      questions: questions('urdu', [
        { type: 'SHORT_ANSWER', prompt: 'لفظ ”خوبصورت“ کا مترادف لکھیں۔', marks: 1, language: 'ur', direction: 'rtl', maxLength: 200 },
        mcq('لفظ ”دن“ کا متضاد منتخب کریں۔', ['صبح', 'رات', 'دوپہر', 'روشنی'], 'ur', 'rtl'),
        { type: 'SHORT_ANSWER', prompt: 'لفظ ”کتاب“ کی جمع لکھیں۔', marks: 1, language: 'ur', direction: 'rtl', maxLength: 200 },
      ]),
    },
  ],
};
