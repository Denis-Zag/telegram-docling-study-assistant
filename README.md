# Telegram Docling Study Assistant

В этом проекте я реализовал Telegram-бота, который превращает загруженные PDF и
DOCX в персональную базу знаний. Docling извлекает структуру документа и
разбивает её на чанки, ProxyAPI создаёт embeddings, Pinecone хранит данные, а
Haystack-пайплайн находит подходящие фрагменты и формирует ответ с указанием
источников.

## Что умеет бот

- принимает PDF и DOCX через Telegram;
- обрабатывает документы локально через Docling;
- сохраняет структурные чанки и метаданные в Pinecone;
- создаёт embeddings через ProxyAPI, без локальной `sentence-transformers`;
- после загрузки отправляет резюме документа ровно в одном предложении;
- отвечает на вопросы только по найденным фрагментам;
- один раз повторяет поиск при временном таймауте Pinecone;
- показывает только те файлы и страницы, которые модель указала как основание ответа;
- изолирует данные пользователей отдельными Pinecone `namespace`;
- удаляет материалы текущего пользователя командой `/clear`.

## Как устроены пайплайны

### Загрузка документа

```text
PDF или DOCX
    ↓
DoclingDocumentConverter
    ├── структурные чанки → OpenAIDocumentEmbedder → Pinecone DocumentWriter
    └── текст документа → SummaryPromptBuilder → OpenAIChatGenerator → резюме
```

### Ответ на вопрос

```text
Вопрос пользователя
    ↓
OpenAITextEmbedder
    ↓
PineconeEmbeddingRetriever
    ↓
StudyAnswerPromptBuilder
    ↓
OpenAIChatGenerator
    ↓
Ответ и минимальный список использованных источников
```

Оба процесса я собрал как явные `Haystack Pipeline`, а не как последовательность
несвязанных ручных вызовов.

## Данные и безопасность

Для каждого Telegram-пользователя я создаю отдельный Pinecone `namespace`.
Открытый Telegram ID я не сохраняю в его названии: вместо него используется
SHA-256-хеш.

В Pinecone сохраняются:

- текст чанка;
- идентификатор документа;
- название исходного файла;
- номер чанка;
- номера страниц, если они доступны;
- заголовок раздела, если его определил Docling.

Исходный файл находится во временной папке только во время обработки и удаляется
после завершения пайплайна. Ключи и токены читаются из `.env`, который исключён
из Git.

В проекте я не использую секретные или чувствительные
документы.

## Стек

- Python 3.12;
- Haystack 3.3;
- Docling 2;
- Pinecone и `pinecone-haystack`;
- ProxyAPI с OpenAI-совместимым API;
- pyTelegramBotAPI;
- Pydantic Settings, Loguru;
- pytest и Ruff.

## Структура проекта

```text
.
├── app/
│   ├── components/
│   │   ├── docling_converter.py  # Docling и подготовка метаданных
│   │   └── prompts.py            # промпты резюме и RAG-ответа
│   ├── pipelines/
│   │   ├── ingestion.py          # загрузка, embeddings, Pinecone, резюме
│   │   └── generation.py         # поиск и генерация ответа
│   ├── config.py                 # настройки окружения
│   ├── document_store.py         # изоляция Pinecone namespace
│   ├── services.py               # сборка зависимостей
│   ├── study_assistant.py        # прикладная логика
│   └── telegram_bot.py           # Telegram-обработчики
├── tests/                        # офлайн-тесты
├── bot.py                        # запуск polling
├── preflight.py                  # живая проверка без polling
├── .env.example
├── requirements.txt
└── requirements-dev.txt
```

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Полный Docling устанавливает локальные библиотеки распознавания и может занять
заметное место. Кеш Docling и Hugging Face направляется в `.cache` внутри
проекта; RapidOCR может хранить свои модели внутри `.venv`. Обе папки исключены
из Git. При первом анализе PDF Docling может дополнительно загрузить модели.

## Настройка

Для локальной настройки я создаю файл окружения командой:

```powershell
Copy-Item .env.example .env
```

Затем я заполняю три секретных значения только в локальном `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=
PROXYAPI_KEY=
PINECONE_API_KEY=
```

Основные несекретные настройки:

- чат-модель: `openai/gpt-4o-mini`;
- embedding-модель: `openai/text-embedding-3-small`;
- размерность Pinecone: `1536`;
- индекс: `telegram-docling-study-assistant`;
- метрика: `cosine`;
- число найденных фрагментов: `8`.

## Офлайн-проверка

```powershell
python -m pytest -q --basetemp .pytest-tmp -p no:cacheprovider
python -m ruff check .
python -m compileall -q app bot.py preflight.py tests
python -m pip check
```

Офлайн-тесты не обращаются к Telegram, ProxyAPI или Pinecone.

## Живая проверка без polling

```powershell
python preflight.py .\test_document.pdf
```

С помощью этой команды я проверяю полный сценарий: Telegram `getMe`, разбор документа Docling,
создание embeddings через ProxyAPI, запись и поиск в Pinecone, резюме и ответ по
документу. Для неё используется отдельный временный namespace, который очищается
в блоке `finally`.

Для демонстрации я использую нейтральное техническое описание собственного
проекта:

- `output/pdf/Auto_Service_AI_Triage_Overview.pdf` - файл для загрузки в бота;
- `docs/HOMEWORK_TEST_SCENARIO.md` - последовательность проверки и список
  рекомендуемых скриншотов;
- `TEST_RESULTS.md` - итоговый отчёт о проверках и фактических ответах бота.

## Запуск

```powershell
python bot.py
```

На одном Telegram-токене должен работать только один polling-процесс.

## Проверочный сценарий домашнего задания

1. Я отправляю `/start`.
2. Загружаю тестовый PDF или DOCX и дожидаюсь резюме.
3. Задаю вопрос, ответ на который точно есть в документе.
4. Проверяю название файла и страницу в списке источников.
5. Выполняю `/document_status` и проверяю количество сохранённых чанков.
6. Выполняю `/clear` и убеждаюсь, что база знаний очищена.
7. Отдельно проверяю изоляцию с двух Telegram-аккаунтов.
8. Делаю скриншоты загрузки, резюме и ответа по документу.

## Текущий статус

Я завершил основной сценарий проекта. Демонстрационный PDF преобразован в 14
фрагментов. Бот корректно ответил на два контрольных вопроса, сослался только на
нужные страницы 2 и 3, а на вопрос о стоимости букета не стал придумывать ответ.
Все фактические результаты записаны в `TEST_RESULTS.md`.
