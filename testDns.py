import dns.message
import dns.query

def test_local_dns(query_domain="youtube.com", server="127.0.0.1"):
    print(f"Testing DNS Server at {server} for domain: {query_domain}...")

    # 1. Create a standard DNS query message
    query = dns.message.make_query(query_domain, dns.rdatatype.A)

    try:
        # 2. Send the UDP query to our local forwarder
        # timeout=5 ensures the script doesn't hang if the server isn't running
        response = dns.query.udp(query, server, timeout=5)

        # 3. Parse and display the answers
        print("\n--- Response Received ---")
        for answer in response.answer:
            print(answer.to_text())

    except dns.exception.Timeout:
        print("Error: The request timed out. Is your DNS forwarder running?")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_local_dns()