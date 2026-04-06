# Package gen provides hand-written gRPC types and stubs for the MIRASTACK
# plugin protocol. These mirror the protobuf definitions in plugin.proto but
# are hand-written to avoid a protoc/grpcio-tools dependency during early
# development. When buf generate is run for Python, this package will be
# replaced by generated code.
