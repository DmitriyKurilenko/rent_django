"""
Генерация PDF договоров из HTML-шаблонов через WeasyPrint.
"""
import hashlib
import io
import logging
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.template import Template, Context
from django.utils import timezone

logger = logging.getLogger(__name__)

# Базовый HTML-шаблон договора (используется если ContractTemplate ещё не создан)
DEFAULT_AGENT_RENTAL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page { size: A4; margin: 2cm; }
    body { font-family: 'DejaVu Sans', sans-serif; font-size: 12px; line-height: 1.6; color: #333; }
    h1 { text-align: center; font-size: 18px; margin-bottom: 5px; }
    h2 { font-size: 14px; margin-top: 20px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
    .contract-number { text-align: center; font-size: 13px; color: #666; margin-bottom: 20px; }
    .contract-date { text-align: center; font-size: 12px; color: #666; margin-bottom: 30px; }
    table { width: 100%; border-collapse: collapse; margin: 10px 0; }
    td, th { padding: 6px 8px; border: 1px solid #ddd; font-size: 11px; }
    th { background-color: #f5f5f5; text-align: left; }
    .parties { margin: 15px 0; }
    .parties td { border: none; vertical-align: top; padding: 4px 8px; }
    .signature-block { margin-top: 40px; page-break-inside: avoid; }
    .signature-line { border-bottom: 1px solid #333; width: 200px; display: inline-block; margin-top: 30px; }
    .section { margin: 15px 0; }
    .highlight { background-color: #f9f9f9; padding: 10px; border-left: 3px solid #2196F3; margin: 10px 0; }
    .footer { text-align: center; font-size: 9px; color: #999; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; }
</style>
</head>
<body>

<h1>АГЕНТСКИЙ ДОГОВОР</h1>
<p class="contract-number">№ {{ contract_number }}</p>
<p class="contract-date">от {{ contract_date }}</p>

<div class="parties">
<table>
<tr>
    <td style="width:50%;">
        <strong>Агент:</strong><br>
        {{ agent_full_name }}<br>
        {% if agent_company %}{{ agent_company }}<br>{% endif %}
        Тел: {{ agent_phone }}
    </td>
    <td style="width:50%;">
        <strong>Заказчик (Принципал):</strong><br>
        {{ signer_full_name }}<br>
        Документ: {{ signer_passport }}<br>
        Адрес: {{ signer_address }}<br>
        Тел: {{ signer_phone }}<br>
        Email: {{ signer_email }}
    </td>
</tr>
</table>
</div>

<h2>1. Предмет договора</h2>
<div class="section">
<p>1.1. Агент обязуется по поручению Заказчика за вознаграждение совершить от своего имени,
но за счёт Заказчика, юридические и иные действия по организации аренды яхты (судна)
для Заказчика на следующих условиях:</p>

<div class="highlight">
<table>
<tr><th>Яхта</th><td>{{ boat_title }}</td></tr>
<tr><th>Локация</th><td>{{ boat_location }}</td></tr>
{% if boat_manufacturer %}<tr><th>Производитель / Модель</th><td>{{ boat_manufacturer }} {{ boat_model }}</td></tr>{% endif %}
{% if boat_year %}<tr><th>Год выпуска</th><td>{{ boat_year }}</td></tr>{% endif %}
<tr><th>Период аренды</th><td>{{ check_in }} — {{ check_out }} ({{ rental_days }} дн.)</td></tr>
<tr><th>Стоимость аренды</th><td>{{ total_price }} {{ currency }}</td></tr>
{% if has_meal %}<tr><th>Питание</th><td>Включено</td></tr>{% endif %}
</table>
</div>
</div>

<h2>2. Обязанности сторон</h2>
<div class="section">
<p>2.1. Агент обязуется:</p>
<p>— обеспечить бронирование указанной яхты на указанный период;</p>
<p>— предоставить Заказчику всю необходимую информацию об условиях аренды;</p>
<p>— содействовать в решении вопросов, связанных с арендой яхты.</p>

<p>2.2. Заказчик обязуется:</p>
<p>— оплатить стоимость аренды и агентское вознаграждение в установленные сроки;</p>
<p>— предоставить достоверные персональные данные;</p>
<p>— соблюдать правила эксплуатации яхты и требования безопасности.</p>
</div>

<h2>3. Стоимость услуг и порядок оплаты</h2>
<div class="section">
<p>3.1. Общая стоимость аренды составляет <strong>{{ total_price }} {{ currency }}</strong>.</p>
<p>3.2. Оплата производится в порядке, согласованном сторонами.</p>
</div>

<h2>4. Ответственность сторон</h2>
<div class="section">
<p>4.1. Стороны несут ответственность за неисполнение или ненадлежащее исполнение
обязательств по настоящему договору в соответствии с действующим законодательством.</p>
<p>4.2. Агент не несёт ответственности за действия третьих лиц (чартерной компании,
экипажа и пр.), а также за обстоятельства непреодолимой силы.</p>
</div>

<h2>5. Срок действия и расторжение</h2>
<div class="section">
<p>5.1. Договор вступает в силу с момента его подписания обеими сторонами и действует
до полного исполнения обязательств.</p>
<p>5.2. Досрочное расторжение возможно по соглашению сторон или в одностороннем порядке
с уведомлением другой стороны не менее чем за 14 дней.</p>
</div>

{% if additional_terms %}
<h2>6. Дополнительные условия</h2>
<div class="section">
<p>{{ additional_terms }}</p>
</div>
{% endif %}

<h2>{% if additional_terms %}7{% else %}6{% endif %}. Заключительные положения</h2>
<div class="section">
<p>Настоящий договор составлен в электронной форме. Стороны признают юридическую силу
простой электронной подписи в соответствии с Федеральным законом № 63-ФЗ
«Об электронной подписи» и соглашением сторон.</p>
<p>Все споры разрешаются путём переговоров, при невозможности — в суде по месту
нахождения ответчика.</p>
</div>

<div class="signature-block">
<table class="parties">
<tr>
    <td style="width:50%;">
        <strong>Агент:</strong><br><br>
        {{ agent_full_name }}<br>
        <span class="signature-line">&nbsp;</span><br>
        <small>Подпись</small>
    </td>
    <td style="width:50%;">
        <strong>Заказчик:</strong><br><br>
        {{ signer_full_name }}<br>
        <span class="signature-line">&nbsp;</span><br>
        <small>Подпись</small>
    </td>
</tr>
</table>
</div>

<div class="footer">
Документ сформирован {{ generation_date }}. Хэш документа: {{ document_hash }}
</div>

</body>
</html>
"""


def build_contract_context(contract):
    """Собирает контекст для рендеринга шаблона договора из объекта Contract."""
    booking = contract.booking
    offer = contract.offer
    data = contract.contract_data

    boat_data = booking.boat_data or {}
    boat_info = boat_data.get('boat_info', {})

    check_in = booking.start_date
    check_out = booking.end_date
    rental_days = (check_out - check_in).days if check_in and check_out else 0

    return {
        'contract_number': contract.contract_number,
        'contract_date': contract.created_at.strftime('%d.%m.%Y'),
        'generation_date': timezone.now().strftime('%d.%m.%Y %H:%M UTC'),

        # Агент
        'agent_full_name': data.get('agent_full_name', ''),
        'agent_company': data.get('agent_company', ''),
        'agent_phone': data.get('agent_phone', ''),

        # Клиент
        'signer_full_name': data.get('signer_full_name', ''),
        'signer_passport': data.get('signer_passport', ''),
        'signer_address': data.get('signer_address', ''),
        'signer_phone': data.get('signer_phone', ''),
        'signer_email': data.get('signer_email', ''),

        # Яхта
        'boat_title': boat_info.get('title', booking.boat_title or ''),
        'boat_location': boat_info.get('location', ''),
        'boat_manufacturer': boat_info.get('manufacturer', ''),
        'boat_model': boat_info.get('model', ''),
        'boat_year': boat_info.get('year', ''),

        # Условия
        'check_in': check_in.strftime('%d.%m.%Y') if check_in else '',
        'check_out': check_out.strftime('%d.%m.%Y') if check_out else '',
        'rental_days': rental_days,
        'total_price': f"{booking.total_price:,.2f}",
        'currency': booking.currency,
        'has_meal': offer.has_meal if offer else False,
        'additional_terms': data.get('additional_terms', ''),

        'document_hash': '',  # заполняется после генерации
    }


def generate_contract_pdf(contract):
    """
    Генерирует PDF документ для договора через WeasyPrint.
    Возвращает (pdf_bytes, sha256_hash).
    """
    from weasyprint import HTML

    # Получить шаблон
    if contract.template and contract.template.template_content:
        template_str = contract.template.template_content
    else:
        template_str = DEFAULT_AGENT_RENTAL_TEMPLATE

    context = build_contract_context(contract)

    # Первый проход: рендерим без хэша
    template = Template(template_str)
    html = template.render(Context(context))

    # Вычисляем хэш HTML
    doc_hash = hashlib.sha256(html.encode('utf-8')).hexdigest()
    context['document_hash'] = doc_hash

    # Второй проход: рендерим с хэшем
    html = template.render(Context(context))

    # Конвертируем HTML -> PDF через WeasyPrint
    pdf_bytes = HTML(string=html).write_pdf()

    if not pdf_bytes:
        logger.error(f"[Contract] PDF generation error for {contract.contract_number}")
        raise RuntimeError("Ошибка генерации PDF")

    logger.info(f"[Contract] PDF generated for {contract.contract_number}, "
                f"size={len(pdf_bytes)} bytes, hash={doc_hash[:16]}...")

    return pdf_bytes, doc_hash


def generate_and_save_pdf(contract):
    """Генерирует PDF и сохраняет его в модель Contract."""
    pdf_bytes, doc_hash = generate_contract_pdf(contract)

    filename = f"contract_{contract.contract_number}.pdf"
    contract.document_file.save(filename, ContentFile(pdf_bytes), save=False)
    contract.document_hash = doc_hash
    contract.save(update_fields=['document_file', 'document_hash', 'updated_at'])

    logger.info(f"[Contract] Saved PDF for {contract.contract_number}")
    return contract
