# Movie Recommender

Sustav za preporuku filmova.
Projekt je dio kolegija Infrastruktura podataka velikog obujma (IPVO) na Fakultetu Informatike i Digitalnih tehnologija.

Faza 1: Backend servis + baza podataka + skalabilnost.
Baza se pokreće s docker compose up --build i onda se testira na http://localhost
Frontend za prvu fazu napravio kolega DMatuhanca. Login i register funkcionalnosti.

Faza 2: Batch processor i dataset za future ML training (MinIO)
Sustav uzima ratings i movie_id filmova kako bi sakupio podatke za sustav preporuke filmova.
S pokretanjem dockera pokreće se i batch processing koji se obrađuje jednom, zatim se pokreće MinIO na stranici http://localhost:9001
