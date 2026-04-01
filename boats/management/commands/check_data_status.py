"""
Полная диагностика заполненности данных проекта.

Использование:
  python manage.py check_data_status
  python manage.py check_data_status --full
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.models import UserProfile
from boats.models import (
    Booking, BoatDescription, BoatDetails, BoatGallery, BoatPrice,
    BoatTechnicalSpecs, Charter, Client, Contract, ContractTemplate,
    CountryPriceConfig, Offer, ParsedBoat, PriceSettings,
)


def _pct(part, total):
    return f'{part / total * 100:.1f}%' if total else '—'


class Command(BaseCommand):
    help = 'Полная диагностика заполненности данных'

    def add_arguments(self, parser):
        parser.add_argument(
            '--full', action='store_true',
            help='Подробный вывод: топы, разбивка по языкам, статусы',
        )

    def handle(self, *args, **options):
        full = options['full']

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('  ДИАГНОСТИКА ДАННЫХ')
        self.stdout.write('=' * 60)

        self._check_parsed_boats(full)
        self._check_charters(full)
        self._check_geodata(full)
        self._check_technical_specs(full)
        self._check_gallery(full)
        self._check_prices(full)
        self._check_details(full)
        self._check_offers(full)
        self._check_bookings(full)
        self._check_clients(full)
        self._check_contracts(full)
        self._check_users(full)
        self._check_price_settings(full)

        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('  ГОТОВО')
        self.stdout.write('=' * 60 + '\n')

    # ------------------------------------------------------------------ #
    #  ParsedBoat (основная таблица)
    # ------------------------------------------------------------------ #
    def _check_parsed_boats(self, full):
        from datetime import timedelta
        total = ParsedBoat.objects.count()
        cutoff = timezone.now() - timedelta(days=30)
        active = ParsedBoat.objects.filter(last_parsed__gte=cutoff).count()
        stale = total - active
        with_data = ParsedBoat.objects.exclude(boat_data={}).exclude(boat_data__isnull=True).count()
        with_preview = ParsedBoat.objects.exclude(preview_cdn_url='').count()
        with_manufacturer = ParsedBoat.objects.exclude(manufacturer='').count()
        with_year = ParsedBoat.objects.filter(year__isnull=False).count()
        with_coords = ParsedBoat.objects.filter(latitude__isnull=False, longitude__isnull=False).count()
        with_category = ParsedBoat.objects.exclude(category='').count()
        with_reviews = ParsedBoat.objects.filter(reviews_score__isnull=False).count()
        failed = ParsedBoat.objects.filter(last_parse_success=False).count()

        self.stdout.write('\n── ЛОДКИ (ParsedBoat) ──────────────────────')
        self.stdout.write(f'  Всего:                     {total:,}')
        self.stdout.write(f'  Активные (≤30д):           {active:,}  ({_pct(active, total)})')
        self.stdout.write(f'  Устаревшие (>30д):         {stale:,}  ({_pct(stale, total)})')
        self.stdout.write(f'  С boat_data (не пуст):     {with_data:,}  ({_pct(with_data, total)})')
        self.stdout.write(f'  С превью на CDN:           {with_preview:,}  ({_pct(with_preview, total)})')
        self.stdout.write(f'  С производителем:          {with_manufacturer:,}  ({_pct(with_manufacturer, total)})')
        self.stdout.write(f'  С годом выпуска:           {with_year:,}  ({_pct(with_year, total)})')
        self.stdout.write(f'  С координатами:            {with_coords:,}  ({_pct(with_coords, total)})')
        self.stdout.write(f'  С категорией:              {with_category:,}  ({_pct(with_category, total)})')
        self.stdout.write(f'  С рейтингом:               {with_reviews:,}  ({_pct(with_reviews, total)})')
        self.stdout.write(f'  Неудачный парсинг:         {failed:,}')

        if full:
            cats = (
                ParsedBoat.objects
                .exclude(category='')
                .values('category')
                .annotate(cnt=Count('id'))
                .order_by('-cnt')[:10]
            )
            if cats:
                self.stdout.write('\n  Топ-10 категорий:')
                for row in cats:
                    self.stdout.write(f'    {row["category"]:<30} {row["cnt"]:>6}')

    # ------------------------------------------------------------------ #
    #  Чартеры
    # ------------------------------------------------------------------ #
    def _check_charters(self, full):
        total = ParsedBoat.objects.count()
        with_charter = ParsedBoat.objects.filter(charter__isnull=False).count()
        without_charter = total - with_charter

        # Оценка актуальности каталога: лодки, обновлявшиеся за последние 30 дней
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=30)
        active_boats = ParsedBoat.objects.filter(last_parsed__gte=cutoff).count()
        active_with_charter = ParsedBoat.objects.filter(
            last_parsed__gte=cutoff, charter__isnull=False
        ).count()
        stale_no_charter = ParsedBoat.objects.filter(
            charter__isnull=True, last_parsed__lt=cutoff
        ).count()
        fresh_no_charter = without_charter - stale_no_charter

        self.stdout.write('\n── ЧАРТЕРЫ ─────────────────────────────────')
        self.stdout.write(f'  Всего лодок:               {total:,}')
        self.stdout.write(f'  С привязанным чартером:    {with_charter:,}  ({_pct(with_charter, total)})')
        self.stdout.write(f'  Без чартера (всего):       {without_charter:,}  ({_pct(without_charter, total)})')
        self.stdout.write(f'    — из них устаревшие (>30д без обновления): {stale_no_charter:,}')
        self.stdout.write(f'    — из них свежие (нужна привязка):          {fresh_no_charter:,}')
        self.stdout.write(f'  Активный каталог (≤30д):   {active_boats:,}')
        if active_boats:
            self.stdout.write(
                f'  Чартер в активном каталоге: {active_with_charter:,}  '
                f'({_pct(active_with_charter, active_boats)})'
            )

        charters_total = Charter.objects.count()
        used = Charter.objects.filter(boats__isnull=False).distinct().count()
        self.stdout.write(f'  Чартерных компаний:        {charters_total}')
        self.stdout.write(f'  Из них привязаны к лодкам: {used}')

        if full and with_charter > 0:
            self.stdout.write('\n  Топ-10 чартеров по числу лодок:')
            top = (
                Charter.objects
                .annotate(boat_count=Count('boats'))
                .filter(boat_count__gt=0)
                .order_by('-boat_count')[:10]
            )
            for c in top:
                self.stdout.write(f'    {c.name:<40} {c.boat_count:>5} лодок  ({c.commission}%)')

    # ------------------------------------------------------------------ #
    #  Геоданные
    # ------------------------------------------------------------------ #
    def _check_geodata(self, full):
        total_desc = BoatDescription.objects.count()
        with_country = BoatDescription.objects.exclude(country='').count()
        with_region = BoatDescription.objects.exclude(region='').count()
        with_city = BoatDescription.objects.exclude(city='').count()
        with_marina = BoatDescription.objects.exclude(marina='').count()

        boats_total = ParsedBoat.objects.count()
        boats_with_geo = (
            ParsedBoat.objects
            .filter(descriptions__country__gt='')
            .distinct()
            .count()
        )

        self.stdout.write('\n── ГЕОДАННЫЕ ───────────────────────────────')
        self.stdout.write(f'  BoatDescription записей:   {total_desc:,}')
        if total_desc:
            self.stdout.write(f'  С country:                 {with_country:,}  ({_pct(with_country, total_desc)})')
            self.stdout.write(f'  С region:                  {with_region:,}  ({_pct(with_region, total_desc)})')
            self.stdout.write(f'  С city:                    {with_city:,}  ({_pct(with_city, total_desc)})')
            self.stdout.write(f'  С marina:                  {with_marina:,}  ({_pct(with_marina, total_desc)})')
        self.stdout.write(f'  Уникальных лодок с гео:    {boats_with_geo:,} / {boats_total:,}  ({_pct(boats_with_geo, boats_total)})')

        if full:
            self._geodata_by_language()
            self._top_countries()

    def _geodata_by_language(self):
        self.stdout.write('\n  По языкам:')
        langs = (
            BoatDescription.objects
            .values('language')
            .annotate(
                total=Count('id'),
                has_country=Count('id', filter=~Q(country='')),
                has_marina=Count('id', filter=~Q(marina='')),
            )
            .order_by('language')
        )
        self.stdout.write(f'    {"Язык":<8} {"Всего":>7} {"Страна":>8} {"Марина":>8}')
        self.stdout.write(f'    {"─"*8} {"─"*7} {"─"*8} {"─"*8}')
        for row in langs:
            lang = row['language']
            t = row['total']
            c = row['has_country']
            m = row['has_marina']
            c_pct = f'{c/t*100:.0f}%' if t else '—'
            m_pct = f'{m/t*100:.0f}%' if t else '—'
            self.stdout.write(
                f'    {lang:<8} {t:>7,} {c:>5} ({c_pct:>3}) {m:>5} ({m_pct:>3})'
            )

    def _top_countries(self):
        self.stdout.write('\n  Топ-15 стран (en_EN):')
        top = (
            BoatDescription.objects
            .filter(language='en_EN')
            .exclude(country='')
            .values('country')
            .annotate(cnt=Count('id'))
            .order_by('-cnt')[:15]
        )
        for row in top:
            self.stdout.write(f'    {row["country"]:<30} {row["cnt"]:>5}')

    # ------------------------------------------------------------------ #
    #  Технические характеристики
    # ------------------------------------------------------------------ #
    def _check_technical_specs(self, full):
        boats_total = ParsedBoat.objects.count()
        specs_total = BoatTechnicalSpecs.objects.count()
        with_length = BoatTechnicalSpecs.objects.filter(length__isnull=False).count()
        with_cabins = BoatTechnicalSpecs.objects.filter(cabins__isnull=False).count()
        with_engine = BoatTechnicalSpecs.objects.exclude(engine_type='').count()
        with_speed = BoatTechnicalSpecs.objects.filter(max_speed__isnull=False).count()

        self.stdout.write('\n── ТЕХНИЧЕСКИЕ ХАРАКТЕРИСТИКИ ──────────────')
        self.stdout.write(f'  Лодок со спеками:          {specs_total:,} / {boats_total:,}  ({_pct(specs_total, boats_total)})')
        if specs_total:
            self.stdout.write(f'  С длиной:                  {with_length:,}  ({_pct(with_length, specs_total)})')
            self.stdout.write(f'  С каютами:                 {with_cabins:,}  ({_pct(with_cabins, specs_total)})')
            self.stdout.write(f'  С типом двигателя:         {with_engine:,}  ({_pct(with_engine, specs_total)})')
            self.stdout.write(f'  С макс. скоростью:         {with_speed:,}  ({_pct(with_speed, specs_total)})')

    # ------------------------------------------------------------------ #
    #  Галерея
    # ------------------------------------------------------------------ #
    def _check_gallery(self, full):
        boats_total = ParsedBoat.objects.count()
        photos_total = BoatGallery.objects.count()
        boats_with_photos = (
            ParsedBoat.objects
            .filter(gallery__isnull=False)
            .distinct()
            .count()
        )
        avg_photos = photos_total / boats_with_photos if boats_with_photos else 0

        self.stdout.write('\n── ГАЛЕРЕЯ ─────────────────────────────────')
        self.stdout.write(f'  Всего фото:                {photos_total:,}')
        self.stdout.write(f'  Лодок с фото:              {boats_with_photos:,} / {boats_total:,}  ({_pct(boats_with_photos, boats_total)})')
        self.stdout.write(f'  Среднее фото/лодку:        {avg_photos:.1f}')

    # ------------------------------------------------------------------ #
    #  Цены (BoatPrice)
    # ------------------------------------------------------------------ #
    def _check_prices(self, full):
        boats_total = ParsedBoat.objects.count()
        prices_total = BoatPrice.objects.count()
        boats_with_price = (
            ParsedBoat.objects
            .filter(prices__isnull=False)
            .distinct()
            .count()
        )

        self.stdout.write('\n── ЦЕНЫ (BoatPrice) ────────────────────────')
        self.stdout.write(f'  Всего записей:             {prices_total:,}')
        self.stdout.write(f'  Лодок с ценами:            {boats_with_price:,} / {boats_total:,}  ({_pct(boats_with_price, boats_total)})')

        if full:
            by_currency = (
                BoatPrice.objects
                .values('currency')
                .annotate(cnt=Count('id'))
                .order_by('-cnt')
            )
            if by_currency:
                self.stdout.write('  По валютам:')
                for row in by_currency:
                    self.stdout.write(f'    {row["currency"]:<6} {row["cnt"]:>7,}')

    # ------------------------------------------------------------------ #
    #  Детали (extras, equipment)
    # ------------------------------------------------------------------ #
    def _check_details(self, full):
        boats_total = ParsedBoat.objects.count()
        details_total = BoatDetails.objects.count()
        boats_with_details = (
            ParsedBoat.objects
            .filter(details__isnull=False)
            .distinct()
            .count()
        )

        self.stdout.write('\n── ДЕТАЛИ (extras/equipment) ───────────────')
        self.stdout.write(f'  Всего записей:             {details_total:,}')
        self.stdout.write(f'  Лодок с деталями:          {boats_with_details:,} / {boats_total:,}  ({_pct(boats_with_details, boats_total)})')

        if full:
            by_lang = (
                BoatDetails.objects
                .values('language')
                .annotate(cnt=Count('id'))
                .order_by('language')
            )
            if by_lang:
                self.stdout.write('  По языкам:')
                for row in by_lang:
                    self.stdout.write(f'    {row["language"]:<8} {row["cnt"]:>7,}')

    # ------------------------------------------------------------------ #
    #  Офферы
    # ------------------------------------------------------------------ #
    def _check_offers(self, full):
        total = Offer.objects.count()
        active = Offer.objects.filter(is_active=True).count()
        by_type = dict(
            Offer.objects
            .values_list('offer_type')
            .annotate(cnt=Count('id'))
            .order_by()
        )
        total_views = Offer.objects.aggregate(v=Sum('views_count'))['v'] or 0
        with_client = Offer.objects.filter(client__isnull=False).count()

        self.stdout.write('\n── ОФФЕРЫ ──────────────────────────────────')
        self.stdout.write(f'  Всего:                     {total}')
        self.stdout.write(f'  Активных:                  {active}')
        self.stdout.write(f'  Туристических:             {by_type.get("tourist", 0)}')
        self.stdout.write(f'  Капитанских:               {by_type.get("captain", 0)}')
        self.stdout.write(f'  С привязанным клиентом:    {with_client}')
        self.stdout.write(f'  Всего просмотров:          {total_views:,}')

    # ------------------------------------------------------------------ #
    #  Бронирования
    # ------------------------------------------------------------------ #
    def _check_bookings(self, full):
        total = Booking.objects.count()
        by_status = dict(
            Booking.objects
            .values_list('status')
            .annotate(cnt=Count('id'))
            .order_by()
        )
        with_client = Booking.objects.filter(client__isnull=False).count()

        self.stdout.write('\n── БРОНИРОВАНИЯ ────────────────────────────')
        self.stdout.write(f'  Всего:                     {total}')
        for status, label in [('pending', 'Ожидает'), ('confirmed', 'Подтверждено'),
                              ('cancelled', 'Отменено'), ('completed', 'Завершено')]:
            cnt = by_status.get(status, 0)
            if cnt:
                self.stdout.write(f'  {label + ":":27s}{cnt}')
        self.stdout.write(f'  С привязанным клиентом:    {with_client}')

    # ------------------------------------------------------------------ #
    #  Клиенты
    # ------------------------------------------------------------------ #
    def _check_clients(self, full):
        total = Client.objects.count()
        with_passport = Client.objects.exclude(passport_number='').count()
        with_email = Client.objects.exclude(email='').count()

        self.stdout.write('\n── КЛИЕНТЫ ─────────────────────────────────')
        self.stdout.write(f'  Всего:                     {total}')
        self.stdout.write(f'  С паспортом:               {with_passport}')
        self.stdout.write(f'  С email:                   {with_email}')

        if full and total:
            by_agent = (
                Client.objects
                .values('created_by__username')
                .annotate(cnt=Count('id'))
                .order_by('-cnt')[:5]
            )
            self.stdout.write('  По агентам:')
            for row in by_agent:
                self.stdout.write(f'    {row["created_by__username"]:<25} {row["cnt"]:>4}')

    # ------------------------------------------------------------------ #
    #  Договоры
    # ------------------------------------------------------------------ #
    def _check_contracts(self, full):
        total = Contract.objects.count()
        templates = ContractTemplate.objects.count()
        by_status = dict(
            Contract.objects
            .values_list('status')
            .annotate(cnt=Count('id'))
            .order_by()
        )
        now = timezone.now()
        expired_unsigned = Contract.objects.filter(
            expires_at__lt=now,
            status__in=('draft', 'sent', 'viewed'),
        ).count()

        self.stdout.write('\n── ДОГОВОРЫ ────────────────────────────────')
        self.stdout.write(f'  Шаблонов:                  {templates}')
        self.stdout.write(f'  Всего договоров:           {total}')
        for status, label in [('draft', 'Черновик'), ('sent', 'Отправлен'),
                              ('viewed', 'Просмотрен'), ('signed', 'Подписан'),
                              ('rejected', 'Отклонён'), ('expired', 'Истёк')]:
            cnt = by_status.get(status, 0)
            if cnt:
                self.stdout.write(f'  {label + ":":27s}{cnt}')
        if expired_unsigned:
            self.stdout.write(f'  Просрочены (не подписаны): {expired_unsigned}')

    # ------------------------------------------------------------------ #
    #  Пользователи
    # ------------------------------------------------------------------ #
    def _check_users(self, full):
        total = User.objects.count()
        active = User.objects.filter(is_active=True).count()
        by_role = dict(
            UserProfile.objects
            .values_list('role')
            .annotate(cnt=Count('id'))
            .order_by()
        )

        self.stdout.write('\n── ПОЛЬЗОВАТЕЛИ ────────────────────────────')
        self.stdout.write(f'  Всего:                     {total}')
        self.stdout.write(f'  Активных:                  {active}')
        for role, label in [('tourist', 'Турист'), ('captain', 'Капитан'),
                            ('manager', 'Менеджер'), ('admin', 'Админ'),
                            ('superadmin', 'Суперадмин')]:
            cnt = by_role.get(role, 0)
            if cnt:
                self.stdout.write(f'  {label + ":":27s}{cnt}')

    # ------------------------------------------------------------------ #
    #  Настройки цен
    # ------------------------------------------------------------------ #
    def _check_price_settings(self, full):
        ps_total = PriceSettings.objects.count()
        cc_total = CountryPriceConfig.objects.count()
        cc_default = CountryPriceConfig.objects.filter(is_default=True).count()

        self.stdout.write('\n── НАСТРОЙКИ ЦЕН ──────────────────────────')
        self.stdout.write(f'  PriceSettings (по юзерам): {ps_total}')
        self.stdout.write(f'  CountryPriceConfig:        {cc_total}')
        self.stdout.write(f'  Из них default:            {cc_default}')

        if full:
            configs = (
                CountryPriceConfig.objects
                .order_by('-is_default', 'sort_order', 'country_name')
            )
            if configs:
                self.stdout.write('  Конфигурации:')
                for c in configs:
                    default = ' (default)' if c.is_default else ''
                    self.stdout.write(f'    {c.country_name}{default}')
