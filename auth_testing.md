# Auth testing
1. mongosh: use test_database; db.users.findOne({role:"super_admin"}) -> password_hash starts with $2b$; unique index on users.email.
2. curl -c cookies.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"anastaibani53@gmail.com","password":"MMS@Admin2026"}'
3. curl -b cookies.txt $API/api/auth/me -> same user.
4. 5 bad attempts -> 429 lockout for 15 minutes (per ip+email).
5. Deactivated user -> login 403; existing session -> 401.
