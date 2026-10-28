select *
from cotacoes
where
(
(base = :base AND symbol = :symbol)
OR
(base = :symbol AND symbol = :base)
)
AND date(date, 'start of month') = date(:data, 'start of month')