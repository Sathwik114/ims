from ldap3 import Server, Connection, ALL

def ldap_authenticate(username, password):

    host = "10.40.10.204"
    port = 389

    server = Server(host, port=port, get_info=ALL)

    try:
        conn = Connection(
            server,
            user=f"gti\\{username}",
            password=password,
            auto_bind=True
        )

        if conn.bind():
            conn.unbind()
            return True

    except Exception as e:
        print("LDAP error:", e)

    return False