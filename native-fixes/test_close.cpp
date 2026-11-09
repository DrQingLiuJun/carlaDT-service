#include <iostream>
#include <cstdlib>
#include <unistd.h>
#include <rpc/detail/log.h>
#include <rpc/detail/server_session.h>

namespace clmdep_asio { namespace detail {
template<class E> void throw_exception(const E& e) {
  std::cerr << "FATAL_ASIO: " << e.what() << std::endl;
  std::abort();
}
template void throw_exception<std::system_error>(const std::system_error&);
template void throw_exception<std::bad_cast>(const std::bad_cast&);
}}
struct TestSession : rpc::detail::server_session {
  using server_session::server_session;
  int descriptor() { return socket_.native_handle(); }
};
int main() {
  RPCLIB_ASIO::io_service io;
  RPCLIB_ASIO::ip::tcp::socket socket(io);
  socket.open(RPCLIB_ASIO::ip::tcp::v4());
  auto s=std::make_shared<TestSession>(nullptr,&io,std::move(socket),std::make_shared<rpc::detail::dispatcher>(),true);
  // Deterministically simulate a descriptor invalidated during competing closes.
  ::close(s->descriptor());
  s->close();s->close();
  io.run();
  std::cout << "PASS: stale descriptor and duplicate close do not abort" << std::endl;
}
